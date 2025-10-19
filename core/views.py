from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import random
from datetime import date

from .forms import RegisterForm, DepositForm, WithdrawalForm, BankDetailsForm
from .models import PlatformSettings, CustomUser, Level, UserLevel, BankDetails, Deposit, Withdrawal, Task, PlatformBankDetails, Roulette, RouletteSettings

# --- FUNÇÃO AUXILIAR PARA DEFINIR CLASSE E TAXA DE SUBSÍDIO ---
def get_level_class_info(level_id):
    """
    Retorna a classe (A, B, C) e a taxa de subsídio com base no ID do nível.
    Regras:
    - Nível 1-3 -> Classe A (3%)
    - Nível 4-6 -> Classe B (5%)
    - Nível 7+ -> Classe C (7%)
    """
    if 1 <= level_id <= 3:
        return 'A', 0.03
    elif 4 <= level_id <= 6:
        return 'B', 0.05
    elif level_id >= 7:
        return 'C', 0.07
    return 'N/A', 0.0
# --- FIM DA FUNÇÃO AUXILIAR ---


# --- FUNÇÃO ATUALIZADA ---
def home(request):
    if request.user.is_authenticated:
        return redirect('menu')
    else:
        return redirect('cadastro')
# --- FIM DA FUNÇÃO ATUALIZADA ---

def menu(request):
    user_level = None
    levels = Level.objects.all().order_by('deposit_value')

    if request.user.is_authenticated:
        user_level = UserLevel.objects.filter(user=request.user, is_active=True).first()

    try:
        platform_settings = PlatformSettings.objects.first()
        whatsapp_link = platform_settings.whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'

    context = {
        'user_level': user_level,
        'levels': levels,
        'whatsapp_link': whatsapp_link,
    }
    return render(request, 'menu.html', context)

def cadastro(request):
    invite_code_from_url = request.GET.get('invite', None)

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            
            # --- CORREÇÃO AQUI: O NOME DO CAMPO NO FORM É 'invited_by_code' ---
            invited_by_code = form.cleaned_data.get('invited_by_code')
            
            if invited_by_code:
                try:
                    invited_by_user = CustomUser.objects.get(invite_code=invited_by_code)
                    user.invited_by = invited_by_user
                except CustomUser.DoesNotExist:
                    messages.error(request, 'Código de convite inválido.')
                    return render(request, 'cadastro.html', {'form': form})
            
            user.save()
            login(request, user)
            return redirect('menu')
        else:
            try:
                whatsapp_link = PlatformSettings.objects.first().whatsapp_link
            except (PlatformSettings.DoesNotExist, AttributeError):
                whatsapp_link = '#'
            return render(request, 'cadastro.html', {'form': form, 'whatsapp_link': whatsapp_link})
    else:
        # --- CORREÇÃO AQUI: O NOME DO CAMPO NO FORM É 'invited_by_code' ---
        if invite_code_from_url:
            form = RegisterForm(initial={'invited_by_code': invite_code_from_url})
        else:
            form = RegisterForm()
    
    try:
        whatsapp_link = PlatformSettings.objects.first().whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'

    return render(request, 'cadastro.html', {'form': form, 'whatsapp_link': whatsapp_link})

def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('menu')
    else:
        form = AuthenticationForm()

    try:
        whatsapp_link = PlatformSettings.objects.first().whatsapp_link
    except (PlatformSettings.DoesNotExist, AttributeError):
        whatsapp_link = '#'

    return render(request, 'login.html', {'form': form, 'whatsapp_link': whatsapp_link})

@login_required
def user_logout(request):
    logout(request)
    return redirect('menu')

# --- FUNÇÃO DE DEPÓSITO ATUALIZADA PARA O NOVO FLUXO ---
@login_required
def deposito(request):
    platform_bank_details = PlatformBankDetails.objects.all()
    deposit_instruction = PlatformSettings.objects.first().deposit_instruction if PlatformSettings.objects.first() else 'Instruções de depósito não disponíveis.'
    
    # Busca todos os valores de depósito dos Níveis para a Etapa 2
    level_deposits = Level.objects.all().values_list('deposit_value', flat=True).distinct().order_by('deposit_value')
    # Converte os Decimais para strings formatadas para JS
    level_deposits_list = [str(d) for d in level_deposits] 

    if request.method == 'POST':
        # O formulário agora é submetido na Etapa 3
        # Os campos 'amount' e 'proof_of_payment' são necessários
        form = DepositForm(request.POST, request.FILES)
        if form.is_valid():
            deposit = form.save(commit=False)
            deposit.user = request.user
            deposit.save()
            
            # Não exibe mensagem aqui, mas sim no template
            # O template irá exibir uma tela de sucesso após a submissão
            return render(request, 'deposito.html', {
                'platform_bank_details': platform_bank_details,
                'deposit_instruction': deposit_instruction,
                'level_deposits_list': level_deposits_list,
                'deposit_success': True # Variável de contexto para a tela de sucesso
            })
        else:
            messages.error(request, 'Erro ao enviar o depósito. Verifique o valor e o comprovativo.')
    
    # Se não for POST ou se for a primeira vez acessando a página
    form = DepositForm()
    
    context = {
        'platform_bank_details': platform_bank_details,
        'deposit_instruction': deposit_instruction,
        'form': form,
        'level_deposits_list': level_deposits_list,
        'deposit_success': False, # Estado inicial
    }
    return render(request, 'deposito.html', context)
# --- FIM DA FUNÇÃO DE DEPÓSITO ATUALIZADA ---

@login_required
def approve_deposit(request, deposit_id):
    if not request.user.is_staff:
        messages.error(request, 'Você não tem permissão para realizar esta ação.')
        return redirect('menu')

    deposit = get_object_or_404(Deposit, id=deposit_id)
    if not deposit.is_approved:
        deposit.is_approved = True
        deposit.save()
        deposit.user.available_balance += deposit.amount
        deposit.user.save()
        messages.success(request, f'Depósito de {deposit.amount} $ aprovado para {deposit.user.phone_number}. Saldo atualizado.')
    
    return redirect('renda')

@login_required
def saque(request):
    withdrawal_instruction = PlatformSettings.objects.first().withdrawal_instruction if PlatformSettings.objects.first() else 'Instruções de saque não disponíveis.'
    
    withdrawal_records = Withdrawal.objects.filter(user=request.user).order_by('-created_at')
    
    has_bank_details = BankDetails.objects.filter(user=request.user).exists()
    
    if request.method == 'POST':
        form = WithdrawalForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            if not has_bank_details:
                messages.error(request, 'Por favor, adicione suas coordenadas bancárias no seu perfil antes de solicitar um saque.')
                return redirect('perfil')
            
            if amount < 14:
                messages.error(request, 'O valor mínimo para saque é 14 $.')
            elif request.user.available_balance < amount:
                messages.error(request, 'Saldo insuficiente.')
            else:
                withdrawal = Withdrawal.objects.create(user=request.user, amount=amount)
                request.user.available_balance -= amount
                request.user.save()
                messages.success(request, 'Saque solicitado com sucesso. Aguarde a aprovação.')
                return redirect('saque')
    else:
        form = WithdrawalForm()

    context = {
        'withdrawal_instruction': withdrawal_instruction,
        'withdrawal_records': withdrawal_records,
        'form': form,
        'has_bank_details': has_bank_details
    }
    return render(request, 'saque.html', context)

@login_required
def tarefa(request):
    user = request.user
    
    # Encontra o nível ativo do usuário
    active_level = UserLevel.objects.filter(user=user, is_active=True).first()
    has_active_level = active_level is not None
    
    # Define o número de tarefas
    max_tasks = 1
    tasks_completed_today = 0
    
    if has_active_level:
        today = date.today()
        tasks_completed_today = Task.objects.filter(user=user, completed_at__date=today).count()
    
    context = {
        'has_active_level': has_active_level,
        'active_level': active_level,
        'tasks_completed_today': tasks_completed_today,
        'max_tasks': max_tasks,
    }
    return render(request, 'tarefa.html', context)

@login_required
@require_POST
def process_task(request):
    user = request.user
    active_level = UserLevel.objects.filter(user=user, is_active=True).first()

    if not active_level:
        return JsonResponse({'success': False, 'message': 'Você não tem um nível ativo para realizar tarefas.'})

    today = date.today()
    tasks_completed_today = Task.objects.filter(user=user, completed_at__date=today).count()
    max_tasks = 1

    if tasks_completed_today >= max_tasks:
        return JsonResponse({'success': False, 'message': 'Você já concluiu todas as tarefas diárias.'})

    # 1. Ganho do próprio usuário
    earnings = active_level.level.daily_gain
    Task.objects.create(user=user, earnings=earnings)
    user.available_balance += earnings
    
    # 2. Lógica do Subsídio para o Patrocinador (Equipa)
    invited_by_user = user.invited_by
    if invited_by_user:
        # Pega as informações de classe do nível do subordinado
        level_id = active_level.level.id
        level_class, subsidy_rate = get_level_class_info(level_id)
        
        if subsidy_rate > 0:
            # O subsídio é calculado sobre o ganho diário (earnings)
            subsidy_amount = earnings * subsidy_rate
            
            # Credita o subsídio ao patrocinador (invited_by_user)
            invited_by_user.subsidy_balance += subsidy_amount
            invited_by_user.available_balance += subsidy_amount # Adiciona também ao saldo disponível
            invited_by_user.save()

    user.save() # Salva o usuário após creditar o ganho e o subsídio (se houver)

    return JsonResponse({'success': True, 'daily_gain': earnings})

@login_required
def nivel(request):
    levels = Level.objects.all().order_by('deposit_value')
    user_levels = UserLevel.objects.filter(user=request.user, is_active=True).values_list('level__id', flat=True)
    
    if request.method == 'POST':
        level_id = request.POST.get('level_id')
        level_to_buy = get_object_or_404(Level, id=level_id)

        if level_to_buy.id in user_levels:
            messages.error(request, 'Você já possui este nível.')
            return redirect('nivel')
        
        if request.user.available_balance >= level_to_buy.deposit_value:
            request.user.available_balance -= level_to_buy.deposit_value
            UserLevel.objects.create(user=request.user, level=level_to_buy, is_active=True)
            request.user.level_active = True
            request.user.save()
            
            invited_by_user = request.user.invited_by
            if invited_by_user and UserLevel.objects.filter(user=invited_by_user, is_active=True).exists():
                invited_by_user.subsidy_balance += 1000
                invited_by_user.available_balance += 1000
                invited_by_user.save()
                messages.success(request, f'Parabéns! Você recebeu 1000 $ de subsídio por convite de {request.user.phone_number}.')

            messages.success(request, f'Você comprou o nível {level_to_buy.name} com sucesso!')
        else:
            messages.error(request, 'Saldo insuficiente. Por favor, faça um depósito.')
        
        return redirect('nivel')
        
    context = {
        'levels': levels,
        'user_levels': user_levels,
    }
    return render(request, 'nivel.html', context)

@login_required
def equipa(request):
    # Obtém membros diretos
    team_members = CustomUser.objects.filter(invited_by=request.user).order_by('-date_joined')
    team_count = team_members.count()
    
    # Filtros de Classe (Dicionários para facilitar a filtragem no template)
    class_a_members = []
    class_b_members = []
    class_c_members = []
    members_with_class = [] # Lista para todos os membros com dados enriquecidos
    
    # Processa cada membro para determinar sua classe e obter dados de tarefa
    for member in team_members:
        # Obtém o nível ativo para o membro
        active_level = UserLevel.objects.filter(user=member, is_active=True).first()
        
        last_task = Task.objects.filter(user=member).order_by('-completed_at').first()

        member_data = {
            'phone_number': member.phone_number,
            'date_joined': member.date_joined,
            'is_active': member.level_active,
            'level_name': active_level.level.name if active_level else 'N/A',
            'level_id': active_level.level.id if active_level else 0,
            'class_name': 'N/A',
            'subsidy_rate': 0.0,
            'last_task_time': last_task.completed_at if last_task else None
        }
        
        if active_level:
            class_name, subsidy_rate = get_level_class_info(active_level.level.id)
            member_data['class_name'] = class_name
            member_data['subsidy_rate'] = subsidy_rate
            
            if class_name == 'A':
                class_a_members.append(member_data)
            elif class_name == 'B':
                class_b_members.append(member_data)
            elif class_name == 'C':
                class_c_members.append(member_data)
        
        members_with_class.append(member_data) # Adiciona todos para a lista geral
    
    
    context = {
        'team_members': members_with_class, # Contém todos os membros com dados de classe/tarefa
        'team_count': team_count,
        'class_a_members': class_a_members,
        'class_b_members': class_b_members,
        'class_c_members': class_c_members,
        'total_class_a': len(class_a_members),
        'total_class_b': len(class_b_members),
        'total_class_c': len(class_c_members),
        'invite_link': request.build_absolute_uri(reverse('cadastro')) + f'?invite={request.user.invite_code}',
    }
    return render(request, 'equipa.html', context)

@login_required
def roleta(request):
    user = request.user
    
    context = {
        'roulette_spins': user.roulette_spins,
    }
    
    return render(request, 'roleta.html', context)

@login_required
@require_POST
def spin_roulette(request):
    user = request.user

    if not user.roulette_spins or user.roulette_spins <= 0:
        return JsonResponse({'success': False, 'message': 'Você não tem giros disponíveis para a roleta.'})

    user.roulette_spins -= 1
    user.save()
    
    try:
        roulette_settings = RouletteSettings.objects.first()
        
        if roulette_settings and roulette_settings.prizes:
            prizes_from_admin = [int(p.strip()) for p in roulette_settings.prizes.split(',')]
            prizes_weighted = []
            for prize in prizes_from_admin:
                if prize <= 1000:
                    prizes_weighted.extend([prize] * 3)
                else:
                    prizes_weighted.append(prize)
            prize = random.choice(prizes_weighted)
        else:
            prizes = [100, 200, 300, 500, 1000, 2000]
            prize = random.choice(prizes)

    except RouletteSettings.DoesNotExist:
        prizes = [100, 200, 300, 500, 1000, 2000]
        prize = random.choice(prizes)

    Roulette.objects.create(user=user, prize=prize, is_approved=True)

    user.subsidy_balance += prize
    user.available_balance += prize
    user.save()

    return JsonResponse({'success': True, 'prize': prize, 'message': f'Parabéns! Você ganhou {prize} $.'})

@login_required
def sobre(request):
    try:
        platform_settings = PlatformSettings.objects.first()
        history_text = platform_settings.history_text if platform_settings else 'Histórico da plataforma não disponível.'
    except PlatformSettings.DoesNotExist:
        history_text = 'Histórico da plataforma não disponível.'

    return render(request, 'sobre.html', {'history_text': history_text})

@login_required
def perfil(request):
    bank_details, created = BankDetails.objects.get_or_create(user=request.user)
    user_levels = UserLevel.objects.filter(user=request.user, is_active=True)

    if request.method == 'POST':
        form = BankDetailsForm(request.POST, instance=bank_details)
        password_form = PasswordChangeForm(request.user, request.POST)

        if 'update_bank' in request.POST:
            if form.is_valid():
                form.save()
                messages.success(request, 'Detalhes bancários atualizados com sucesso!')
                return redirect('perfil')
            else:
                messages.error(request, 'Ocorreu um erro ao atualizar os detalhes bancários.')

        if 'change_password' in request.POST:
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Sua senha foi alterada com sucesso!')
                return redirect('perfil')
            else:
                messages.error(request, 'Ocorreu um erro ao alterar a senha. Verifique se a senha antiga está correta e a nova senha é válida.')
    else:
        form = BankDetailsForm(instance=bank_details)
        password_form = PasswordChangeForm(request.user)

    context = {
        'form': form,
        'password_form': password_form,
        'user_levels': user_levels,
    }
    return render(request, 'perfil.html', context)

@login_required
def renda(request):
    user = request.user
    
    active_level = UserLevel.objects.filter(user=user, is_active=True).first()

    approved_deposit_total = Deposit.objects.filter(user=user, is_approved=True).aggregate(Sum('amount'))['amount__sum'] or 0
    
    today = date.today()
    daily_income = Task.objects.filter(user=user, completed_at__date=today).aggregate(Sum('earnings'))['earnings__sum'] or 0

    # A linha abaixo foi alterada para corrigir o status para 'Aprovado'
    total_withdrawals = Withdrawal.objects.filter(user=user, status='Aprovado').aggregate(Sum('amount'))['amount__sum'] or 0

    # O total_income já inclui user.subsidy_balance, onde os subsídios da equipa são creditados.
    total_income = (Task.objects.filter(user=user).aggregate(Sum('earnings'))['earnings__sum'] or 0) + user.subsidy_balance
    
    context = {
        'user': user,
        'active_level': active_level,
        'approved_deposit_total': approved_deposit_total,
        'daily_income': daily_income,
        'total_withdrawals': total_withdrawals,
        'total_income': total_income,
    }
    return render(request, 'renda.html', context)

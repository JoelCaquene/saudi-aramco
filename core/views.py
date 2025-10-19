from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, DecimalField
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import random
from datetime import date
from decimal import Decimal # Importar Decimal para cálculos de precisão

from .forms import RegisterForm, DepositForm, WithdrawalForm, BankDetailsForm
from .models import PlatformSettings, CustomUser, Level, UserLevel, BankDetails, Deposit, Withdrawal, Task, PlatformBankDetails, Roulette, RouletteSettings

# --- NOVA FUNÇÃO: CALCULA CLASSE E TAXA DE SUBSÍDIO ---
def get_member_class(level_id):
    """
    Define a classe de investimento e a taxa de subsídio com base no ID do Nível.
    Nível 1-3: Classe A (3%)
    Nível 4-6: Classe B (5%)
    Nível 7+: Classe C (7%)
    """
    # Mapeamento de Classes e Taxas
    if 1 <= level_id <= 3:
        return 'Classe A', Decimal('0.03') # 3%
    elif 4 <= level_id <= 6:
        return 'Classe B', Decimal('0.05') # 5%
    elif level_id >= 7:
        return 'Classe C', Decimal('0.07') # 7%
    return 'Sem Classe', Decimal('0.00')
# --- FIM DA NOVA FUNÇÃO ---

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
            authenticate(request, user)
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

# --- FUNÇÃO DE DEPÓSITO ORIGINAL ---
@login_required
def deposito(request):
    platform_bank_details = PlatformBankDetails.objects.all()
    deposit_settings = PlatformSettings.objects.first()
    deposit_instruction = deposit_settings.deposit_instruction if deposit_settings else 'Instruções de depósito não disponíveis.'
    
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
# --- FIM DA FUNÇÃO DE DEPÓSITO ORIGINAL ---

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
    withdrawal_settings = PlatformSettings.objects.first()
    withdrawal_instruction = withdrawal_settings.withdrawal_instruction if withdrawal_settings else 'Instruções de saque não disponíveis.'
    
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

# --- FUNÇÃO process_task ATUALIZADA PARA DISTRIBUIÇÃO DE SUBSÍDIO ---
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

    # 1. Processar a Tarefa do Usuário (Subordinado)
    earnings = active_level.level.daily_gain
    Task.objects.create(user=user, earnings=earnings)
    user.available_balance += earnings
    user.save()

    # 2. Processar Subsídio para o Convidante (Líder da Equipe)
    invited_by_user = user.invited_by
    if invited_by_user and invited_by_user.is_active:
        level_id = active_level.level.id
        class_name, subsidy_rate = get_member_class(level_id) # Obter classe e taxa
        
        if subsidy_rate > Decimal('0.00'):
            # Calcula subsídio com base nos ganhos da tarefa do subordinado
            subsidy_amount = earnings * subsidy_rate 
            
            # Adicionar o subsídio ao saldo do convidante
            invited_by_user.subsidy_balance += subsidy_amount
            invited_by_user.available_balance += subsidy_amount
            # Atualiza o total de subsídio recebido da equipe (necessário para o template 'equipa.html')
            invited_by_user.team_subsidy_received += subsidy_amount 
            invited_by_user.save()
            
            # Opcional: Adiciona uma mensagem de sucesso para o líder (se ele estiver logado)
            # messages.success(request, f'Subsídio de {subsidy_amount:.2f} $ recebido de {class_name}.') 
        # Se não houver taxa de subsídio (subsidy_rate é 0.0), nada acontece.

    return JsonResponse({'success': True, 'daily_gain': earnings})
# --- FIM DA FUNÇÃO process_task ATUALIZADA ---

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
            
            # Lógica de bónus por convite de 1000$ (Ajuste se for um valor de subsídio fixo)
            invited_by_user = request.user.invited_by
            if invited_by_user and UserLevel.objects.filter(user=invited_by_user, is_active=True).exists():
                bonus_amount = Decimal('1000.00')
                invited_by_user.subsidy_balance += bonus_amount
                invited_by_user.available_balance += bonus_amount
                invited_by_user.save()
                messages.success(request, f'Parabéns! Você recebeu {bonus_amount} $ de subsídio por convite de {request.user.phone_number}.')

            messages.success(request, f'Você comprou o nível {level_to_buy.name} com sucesso!')
        else:
            messages.error(request, 'Saldo insuficiente. Por favor, faça um depósito.')
        
        return redirect('nivel')
        
    context = {
        'levels': levels,
        'user_levels': user_levels,
    }
    return render(request, 'nivel.html', context)

# --- FUNÇÃO equipa CORRIGIDA E COMPLETA (SEM ERRO 500) ---
@login_required
def equipa(request):
    user = request.user
    # Busca apenas membros diretos. Se houver multinível, esta lógica deve ser expandida.
    team_members = CustomUser.objects.filter(invited_by=user).order_by('-date_joined')
    
    # 1. Preparar a estrutura para as classes A, B, C
    team_classes = {
        'A': {'members': [], 'subsidy_total': Decimal('0.00')},
        'B': {'members': [], 'subsidy_total': Decimal('0.00')},
        'C': {'members': [], 'subsidy_total': Decimal('0.00')},
    }
    
    for member in team_members:
        # Pega o nível ativo do membro (se houver)
        member.active_level = UserLevel.objects.filter(user=member, is_active=True).first()
        
        # 2. Dados necessários para o template
        
        # CORREÇÃO CRÍTICA: Remove output_field=DecimalField() para evitar erro 500
        member_earnings_agg = Task.objects.filter(user=member).aggregate(total=Sum('earnings'))
        
        # Pega o resultado da agregação e garante que é um Decimal, se não for None
        total_earnings = member_earnings_agg.get('total')
        if total_earnings is None:
            member.total_tasks_earnings = Decimal('0.00')
        else:
            # Converte para Decimal por segurança
            member.total_tasks_earnings = Decimal(str(total_earnings)) 
        
        
        if member.active_level:
            level_id = member.active_level.level.id
            class_name, subsidy_rate = get_member_class(level_id)
            
            member.class_name = class_name
            
            # Aproximação do subsídio total que o líder ganhou deste membro:
            member.subsidy_received = member.total_tasks_earnings * subsidy_rate
            
            class_key = class_name.split(' ')[1] # Pega 'A', 'B' ou 'C'
            if class_key in team_classes:
                team_classes[class_key]['members'].append(member)
                # Acumula o subsídio total recebido desta classe
                team_classes[class_key]['subsidy_total'] += member.subsidy_received
        else:
             # Membro sem nível ativo, não é incluído nas classes A/B/C
             member.class_name = 'Sem Classe'
             member.subsidy_received = Decimal('0.00')

    # --- Adicionado para corrigir o Erro 500 ---
    # Cria a lista de membros que NÃO investiram, mas que estão no time.
    non_invested_members = [
        member for member in team_members if not member.active_level
    ]
    # ---------------------------------------------
    
    # Total geral do subsídio recebido da equipe (lido do campo do usuário)
    team_subsidy_received_total = getattr(user, 'team_subsidy_received', Decimal('0.00'))
    
    context = {
        'team_members': team_members,
        'team_count': team_members.count(),
        'invite_link': request.build_absolute_uri(reverse('cadastro')) + f'?invite={user.invite_code}',
        'team_classes': team_classes,
        'team_subsidy_received_total': team_subsidy_received_total,
        'non_invested_members': non_invested_members, # ESSENCIAL para o template equipa.html
    }
    return render(request, 'equipa.html', context)
# --- FIM DA FUNÇÃO equipa CORRIGIDA E COMPLETA ---

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
            # Garante que os prêmios são Decimais para consistência
            prizes_from_admin = [Decimal(p.strip()) for p in roulette_settings.prizes.split(',')]
            prizes_weighted = []
            for prize in prizes_from_admin:
                if prize <= 1000:
                    prizes_weighted.extend([prize] * 3)
                else:
                    prizes_weighted.append(prize)
            prize = random.choice(prizes_weighted)
        else:
            prizes = [Decimal('100.00'), Decimal('200.00'), Decimal('300.00'), Decimal('500.00'), Decimal('1000.00'), Decimal('2000.00')]
            prize = random.choice(prizes)

    except RouletteSettings.DoesNotExist:
        prizes = [Decimal('100.00'), Decimal('200.00'), Decimal('300.00'), Decimal('500.00'), Decimal('1000.00'), Decimal('2000.00')]
        prize = random.choice(prizes)

    Roulette.objects.create(user=user, prize=prize, is_approved=True)

    user.subsidy_balance += prize
    user.available_balance += prize
    user.save()

    return JsonResponse({'success': True, 'prize': str(prize), 'message': f'Parabéns! Você ganhou {prize} $.'})

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

    approved_deposit_total = Deposit.objects.filter(user=user, is_approved=True).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    
    today = date.today()
    daily_income = Task.objects.filter(user=user, completed_at__date=today).aggregate(Sum('earnings'))['earnings__sum'] or Decimal('0.00')

    # A linha abaixo foi alterada para corrigir o status para 'Aprovado' (e usar Decimal)
    total_withdrawals = Withdrawal.objects.filter(user=user, status='Aprovado').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    
    # Adicionar o Subsídio da Equipe ao total_income (e usar Decimal)
    team_subsidy_total = getattr(user, 'team_subsidy_received', Decimal('0.00'))
    
    total_task_earnings = Task.objects.filter(user=user).aggregate(Sum('earnings'))['earnings__sum'] or Decimal('0.00')
    total_income = total_task_earnings + user.subsidy_balance + team_subsidy_total
    
    context = {
        'user': user,
        'active_level': active_level,
        'approved_deposit_total': approved_deposit_total,
        'daily_income': daily_income,
        'total_withdrawals': total_withdrawals,
        'total_income': total_income,
        # Você pode adicionar o subsídio da equipe como uma métrica separada aqui, se quiser
        'team_subsidy_total': team_subsidy_total,
    }
    return render(request, 'renda.html', context)

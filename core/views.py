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

# --- FUNÇÃO: CALCULA CLASSE E TAXA DE SUBSÍDIO ---
def get_member_class(level_id):
    """
    Define a classe de investimento e a taxa de subsídio com base no ID do Nível.
    Nível 1-3: Classe A (3%)
    Nível 4-6: Classe B (5%)
    Nível 7+: Classe C (7%)
    """
    # Mapeamento de Classes e Taxas (usando Decimal para precisão)
    if 1 <= level_id <= 3:
        return 'Classe A', Decimal('0.03') # 3%
    elif 4 <= level_id <= 6:
        return 'Classe B', Decimal('0.05') # 5%
    elif level_id >= 7:
        return 'Classe C', Decimal('0.07') # 7%
    return 'Sem Classe', Decimal('0.00')
# --- FIM DA FUNÇÃO ---

# --- FUNÇÕES DE NAVEGAÇÃO E AUTENTICAÇÃO ---
def home(request):
    if request.user.is_authenticated:
        return redirect('menu')
    else:
        return redirect('cadastro')

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

            # O nome do campo no forms.py deve ser 'invited_by_code'
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
            # Reutiliza o contexto para o caso de formulário inválido
            try:
                whatsapp_link = PlatformSettings.objects.first().whatsapp_link
            except (PlatformSettings.DoesNotExist, AttributeError):
                whatsapp_link = '#'
            return render(request, 'cadastro.html', {'form': form, 'whatsapp_link': whatsapp_link})
    else:
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

# --- FUNÇÕES DE TRANSAÇÃO E NÍVEIS ---
@login_required
def deposito(request):
    platform_bank_details = PlatformBankDetails.objects.all()
    deposit_settings = PlatformSettings.objects.first()
    deposit_instruction = deposit_settings.deposit_instruction if deposit_settings else 'Instruções de depósito não disponíveis.'

    # Busca todos os valores de depósito dos Níveis
    level_deposits = Level.objects.all().values_list('deposit_value', flat=True).distinct().order_by('deposit_value')
    # Converte os Decimais para strings formatadas para JS
    level_deposits_list = [str(d) for d in level_deposits]

    if request.method == 'POST':
        form = DepositForm(request.POST, request.FILES)
        if form.is_valid():
            deposit = form.save(commit=False)
            deposit.user = request.user
            deposit.save()

            # Variável de contexto para a tela de sucesso
            return render(request, 'deposito.html', {
                'platform_bank_details': platform_bank_details,
                'deposit_instruction': deposit_instruction,
                'level_deposits_list': level_deposits_list,
                'deposit_success': True 
            })
        else:
            messages.error(request, 'Erro ao enviar o depósito. Verifique o valor e o comprovativo.')
            # Retorna o formulário com erros
            form = DepositForm(request.POST, request.FILES)

    else:
        form = DepositForm()

    context = {
        'platform_bank_details': platform_bank_details,
        'deposit_instruction': deposit_instruction,
        'form': form,
        'level_deposits_list': level_deposits_list,
        'deposit_success': False, # Estado inicial
    }
    return render(request, 'deposito.html', context)

@login_required
def approve_deposit(request, deposit_id):
    if not request.user.is_staff:
        messages.error(request, 'Você não tem permissão para realizar esta ação.')
        return redirect('menu')

    deposit = get_object_or_404(Deposit, id=deposit_id)
    if not deposit.is_approved:
        deposit.is_approved = True
        deposit.save()
        
        # Garante que o saldo seja Decimal antes de somar
        deposit_amount = Decimal(str(deposit.amount))
        request.user.available_balance += deposit_amount
        request.user.save()
        messages.success(request, f'Depósito de {deposit_amount:.2f} $ aprovado para {deposit.user.phone_number}. Saldo atualizado.')

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

            # O valor mínimo deve ser um Decimal para comparação
            min_withdrawal = Decimal('14.00') 
            if amount < min_withdrawal:
                messages.error(request, f'O valor mínimo para saque é {min_withdrawal} $.')
            elif request.user.available_balance < amount:
                messages.error(request, 'Saldo insuficiente.')
            else:
                withdrawal = Withdrawal.objects.create(user=request.user, amount=amount)
                request.user.available_balance -= amount
                request.user.save()
                messages.success(request, 'Saque solicitado com sucesso. Aguarde a aprovação.')
                return redirect('saque')
        # Se o formulário não for válido, ele cai para o contexto abaixo com o formulário e os erros
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
def nivel(request):
    levels = Level.objects.all().order_by('deposit_value')
    # Pega apenas o ID do nível ativo para checagem rápida
    user_levels_ids = UserLevel.objects.filter(user=request.user, is_active=True).values_list('level__id', flat=True)

    if request.method == 'POST':
        level_id = request.POST.get('level_id')
        level_to_buy = get_object_or_404(Level, id=level_id)

        if level_to_buy.id in user_levels_ids:
            messages.error(request, 'Você já possui este nível.')
            return redirect('nivel')
        
        # Usa Decimal para comparação
        deposit_value = Decimal(str(level_to_buy.deposit_value))
        
        if request.user.available_balance >= deposit_value:
            request.user.available_balance -= deposit_value
            
            # Desativa níveis anteriores se houver (lógica de upgrade)
            UserLevel.objects.filter(user=request.user, is_active=True).update(is_active=False)
            
            # Cria o novo nível ativo
            UserLevel.objects.create(user=request.user, level=level_to_buy, is_active=True)
            request.user.level_active = True
            request.user.save()

            # Lógica de bónus por convite de 1000$ (Ajuste se for um valor de subsídio fixo)
            invited_by_user = request.user.invited_by
            if invited_by_user and invited_by_user.level_active: # Verifica se o líder está ativo
                # Usar Decimal para o bônus
                bonus_amount = Decimal('1000.00') 
                invited_by_user.subsidy_balance += bonus_amount
                invited_by_user.available_balance += bonus_amount
                invited_by_user.save()
                messages.success(request, f'Parabéns! Seu líder recebeu {bonus_amount} $ de subsídio por seu investimento.') # Mensagem para o investidor

            messages.success(request, f'Você comprou o nível {level_to_buy.name} com sucesso!')
        else:
            messages.error(request, 'Saldo insuficiente. Por favor, faça um depósito.')

        return redirect('nivel')

    context = {
        'levels': levels,
        'user_levels_ids': user_levels_ids,
    }
    return render(request, 'nivel.html', context)

# --- FUNÇÕES DE TAREFAS E SUBSÍDIO ---
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

    # 1. Processar a Tarefa do Usuário (Subordinado)
    earnings = Decimal(str(active_level.level.daily_gain))
    Task.objects.create(user=user, earnings=earnings)
    user.available_balance += earnings
    user.save()

    # 2. Processar Subsídio para o Convidante (Líder da Equipe)
    invited_by_user = user.invited_by
    # Verifica se o convidante existe e tem um nível ativo para receber subsídio
    if invited_by_user and invited_by_user.level_active: 
        level_id = active_level.level.id
        class_name, subsidy_rate = get_member_class(level_id) # Obter classe e taxa

        if subsidy_rate > Decimal('0.00'):
            # Calcula subsídio com base nos ganhos da tarefa do subordinado
            subsidy_amount = earnings * subsidy_rate

            # Adicionar o subsídio ao saldo do convidante
            invited_by_user.subsidy_balance += subsidy_amount
            invited_by_user.available_balance += subsidy_amount
            # Atualiza o total de subsídio recebido da equipe
            invited_by_user.team_subsidy_received += subsidy_amount
            invited_by_user.save()

    return JsonResponse({'success': True, 'daily_gain': str(earnings)})

@login_required
def equipa(request):
    user = request.user
    # Busca apenas membros diretos.
    team_members = CustomUser.objects.filter(invited_by=user).order_by('-date_joined')

    # 1. Preparar a estrutura para as classes A, B, C
    team_classes = {
        'A': {'members': [], 'subsidy_total': Decimal('0.00')},
        'B': {'members': [], 'subsidy_total': Decimal('0.00')},
        'C': {'members': [], 'subsidy_total': Decimal('0.00')},
    }

    # Lista de membros que não investiram
    non_invested_members = []
    
    # Total de subsídio recebido da equipe para o template
    team_subsidy_received_total = getattr(user, 'team_subsidy_received', Decimal('0.00'))

    for member in team_members:
        # Pega o nível ativo do membro (se houver)
        member.active_level = UserLevel.objects.filter(user=member, is_active=True).first()

        # Calcula ganhos totais de tarefas do membro
        # CORREÇÃO: Usar `Sum('earnings')` e garantir o tipo Decimal
        member_earnings_agg = Task.objects.filter(user=member).aggregate(total=Sum('earnings', output_field=DecimalField()))
        
        total_earnings = member_earnings_agg.get('total')
        member.total_tasks_earnings = total_earnings if total_earnings is not None else Decimal('0.00')

        if member.active_level:
            level_id = member.active_level.level.id
            class_name, subsidy_rate = get_member_class(level_id)

            member.class_name = class_name
            
            # Aproximação do subsídio que o líder ganhou deste membro (Ganhos do Subordinado * Taxa de Subsídio)
            member.subsidy_received = member.total_tasks_earnings * subsidy_rate

            class_key = class_name.split(' ')[1] # Pega 'A', 'B' ou 'C'
            if class_key in team_classes:
                team_classes[class_key]['members'].append(member)
                # Acumula o subsídio total recebido desta classe
                team_classes[class_key]['subsidy_total'] += member.subsidy_received
        else:
            # Membro sem nível ativo é adicionado à lista de inativos
            non_invested_members.append(member)
            member.class_name = 'Sem Classe'
            member.subsidy_received = Decimal('0.00')

    context = {
        'team_count': team_members.count(),
        'invite_link': request.build_absolute_uri(reverse('cadastro')) + f'?invite={user.invite_code}',
        'team_classes': team_classes,
        'team_subsidy_received_total': team_subsidy_received_total,
        'non_invested_members': non_invested_members,
    }
    return render(request, 'equipa.html', context)
# --- FIM DA FUNÇÃO equipa CORRIGIDA E COMPLETA ---

# --- FUNÇÕES DIVERSAS ---
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
            
            # Lógica de ponderação: prêmios menores têm maior chance
            for prize in prizes_from_admin:
                if prize <= Decimal('1000.00'):
                    prizes_weighted.extend([prize] * 3) # Ponderação 3x
                else:
                    prizes_weighted.append(prize) # Ponderação 1x
            
            prize = random.choice(prizes_weighted)
        else:
            # Prêmios padrão (usando Decimal)
            prizes = [Decimal('100.00'), Decimal('200.00'), Decimal('300.00'), Decimal('500.00'), Decimal('1000.00'), Decimal('2000.00')]
            prize = random.choice(prizes)

    except RouletteSettings.DoesNotExist:
        prizes = [Decimal('100.00'), Decimal('200.00'), Decimal('300.00'), Decimal('500.00'), Decimal('1000.00'), Decimal('2000.00')]
        prize = random.choice(prizes)

    Roulette.objects.create(user=user, prize=prize, is_approved=True)

    user.subsidy_balance += prize
    user.available_balance += prize
    user.save()

    return JsonResponse({'success': True, 'prize': str(prize), 'message': f'Parabéns! Você ganhou {prize:.2f} $.'})

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

    form = BankDetailsForm(instance=bank_details)
    password_form = PasswordChangeForm(request.user)

    if request.method == 'POST':
        if 'update_bank' in request.POST:
            form = BankDetailsForm(request.POST, instance=bank_details)
            if form.is_valid():
                form.save()
                messages.success(request, 'Detalhes bancários atualizados com sucesso!')
                return redirect('perfil')
            else:
                messages.error(request, 'Ocorreu um erro ao atualizar os detalhes bancários.')

        if 'change_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Sua senha foi alterada com sucesso!')
                return redirect('perfil')
            else:
                messages.error(request, 'Ocorreu um erro ao alterar a senha. Verifique se a senha antiga está correta e a nova senha é válida.')

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

    # Garantir que todos os valores agregados sejam Decimais (com `output_field`)
    approved_deposit_total = Deposit.objects.filter(user=user, is_approved=True).aggregate(Sum('amount', output_field=DecimalField()))['amount__sum'] or Decimal('0.00')

    today = date.today()
    daily_income = Task.objects.filter(user=user, completed_at__date=today).aggregate(Sum('earnings', output_field=DecimalField()))['earnings__sum'] or Decimal('0.00')

    # Status alterado para 'Aprovado'
    total_withdrawals = Withdrawal.objects.filter(user=user, status='Aprovado').aggregate(Sum('amount', output_field=DecimalField()))['amount__sum'] or Decimal('0.00')

    # Subsídio da Equipe
    team_subsidy_total = getattr(user, 'team_subsidy_received', Decimal('0.00'))

    total_task_earnings = Task.objects.filter(user=user).aggregate(Sum('earnings', output_field=DecimalField()))['earnings__sum'] or Decimal('0.00')
    
    # O total de renda é a soma de Ganhos de Tarefa e todos os Subsídios (incluindo da roleta, que está em `subsidy_balance`)
    total_income = total_task_earnings + user.subsidy_balance 

    context = {
        'user': user,
        'active_level': active_level,
        'approved_deposit_total': approved_deposit_total,
        'daily_income': daily_income,
        'total_withdrawals': total_withdrawals,
        'total_income': total_income,
        'team_subsidy_total': team_subsidy_total,
    }
    return render(request, 'renda.html', context)
    
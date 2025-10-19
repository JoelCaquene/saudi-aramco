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

# --- FUNÇÕES BÁSICAS ---

def home(request):
    if request.user.is_authenticated:
        return redirect('menu')
    else:
        return redirect('cadastro')

# --- FUNÇÃO CORRIGIDA ---
def menu(request):
    user_level = None
    levels = Level.objects.all().order_by('deposit_value')
    
    # Variáveis de Configuração da Plataforma (Inicializadas para evitar erros)
    whatsapp_link = '#'
    app_download_link = '#'

    if request.user.is_authenticated:
        user_level = UserLevel.objects.filter(user=request.user, is_active=True).first()

    try:
        platform_settings = PlatformSettings.objects.first()
        if platform_settings:
            whatsapp_link = platform_settings.whatsapp_link
            
            # --- CORREÇÃO DE ROBUSTEZ APLICADA AQUI ---
            # Se o valor do banco de dados for None/vazio, usa '#' como fallback.
            app_download_link = platform_settings.app_download_link if platform_settings.app_download_link else '#'
            
    except (PlatformSettings.DoesNotExist, AttributeError):
        # Em caso de falha total ao buscar as configurações, mantém os defaults
        whatsapp_link = '#'
        app_download_link = '#'


    context = {
        'user_level': user_level,
        'levels': levels,
        'whatsapp_link': whatsapp_link,
        'app_download_link': app_download_link,
    }
    return render(request, 'menu.html', context)
# --- FIM DA FUNÇÃO CORRIGIDA ---

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
                platform_settings = PlatformSettings.objects.first()
                whatsapp_link = platform_settings.whatsapp_link if platform_settings else '#'
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
        platform_settings = PlatformSettings.objects.first()
        whatsapp_link = platform_settings.whatsapp_link if platform_settings else '#'
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
        platform_settings = PlatformSettings.objects.first()
        whatsapp_link = platform_settings.whatsapp_link if platform_settings else '#'
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
    
    # Lógica robusta para instruções de depósito
    platform_settings = PlatformSettings.objects.first()
    deposit_instruction = platform_settings.deposit_instruction if platform_settings else 'Instruções de depósito não disponíveis.'
    
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
    platform_settings = PlatformSettings.objects.first()
    withdrawal_instruction = platform_settings.withdrawal_instruction if platform_settings else 'Instruções de saque não disponíveis.'
    
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

    earnings = active_level.level.daily_gain
    Task.objects.create(user=user, earnings=earnings)
    user.available_balance += earnings
    user.save()

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
            # Desativa níveis anteriores (opcional, dependendo da sua regra de negócio)
            # UserLevel.objects.filter(user=request.user, is_active=True).update(is_active=False) 
            
            UserLevel.objects.create(user=request.user, level=level_to_buy, is_active=True)
            request.user.level_active = True
            request.user.save()
            
            # Bônus para o convidante
            invited_by_user = request.user.invited_by
            if invited_by_user and UserLevel.objects.filter(user=invited_by_user, is_active=True).exists():
                invited_by_user.subsidy_balance += 11
                invited_by_user.available_balance += 11
                invited_by_user.save()
                # Não é o ideal exibir a mensagem para o usuário que comprou o nível, mas mantém a lógica existente
                # messages.success(request, f'Parabéns! Você recebeu 11 $ de subsídio por convite de {request.user.phone_number}.')

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
    user = request.user

    # 1. Encontra todos os membros da equipe (convidados diretos)
    team_members = CustomUser.objects.filter(invited_by=user).order_by('-date_joined')
    team_count = team_members.count()

    # 2. Obtém todos os Níveis disponíveis
    all_levels = Level.objects.all().order_by('deposit_value')

    # 3. Contabilização por Nível de Investimento
    levels_data = []
    total_investors = 0
    
    # Dicionário para armazenar membros por nível (para exibição no template)
    members_by_level = {} 
    
    # Preenche os dados para cada nível
    for level in all_levels:
        # Filtra membros da equipe que possuem este nível ATIVO
        members_with_level = team_members.filter(userlevel__level=level, userlevel__is_active=True).distinct()
        
        levels_data.append({
            'name': level.name,
            'count': members_with_level.count(),
            'members': members_with_level, 
        })
        members_by_level[level.name] = members_with_level
        total_investors += members_with_level.count()

    # 4. Contabilização de Não Investidores GERAL
    # Membros que NÃO têm NENHUM UserLevel ativo
    non_invested_members = team_members.exclude(userlevel__is_active=True)
    total_non_investors = non_invested_members.count()
    
    # Adiciona a contagem de não investidos na estrutura levels_data para a primeira aba
    levels_data.insert(0, {
        'name': 'Não Investido',
        'count': total_non_investors,
        'members': non_invested_members,
    })

    context = {
        'team_members': team_members, # Membros totais
        'team_count': team_count, # Contagem total de membros
        'invite_link': request.build_absolute_uri(reverse('cadastro')) + f'?invite={user.invite_code}',
        'levels_data': levels_data, # Dados detalhados por nível (para as abas)
        'total_investors': total_investors, # Contagem de investidores
        'total_non_investors': total_non_investors, # Contagem de não investidores
        'subsidy_balance': user.subsidy_balance, # Saldo de Subsídios
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
    
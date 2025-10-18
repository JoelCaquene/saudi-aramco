from django.contrib import admin
from .models import CustomUser, PlatformSettings, Level, BankDetails, Deposit, Withdrawal, Task, Roulette, RouletteSettings, UserLevel, PlatformBankDetails

# Registrando os modelos com classes ModelAdmin personalizadas

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'available_balance', 'subsidy_balance', 'is_staff', 'is_active', 'date_joined', 'roulette_spins')
    search_fields = ('phone_number', 'invite_code')
    list_filter = ('is_staff', 'is_active', 'level_active')

@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'whatsapp_link', 'history_text', 'deposit_instruction', 'withdrawal_instruction')
    search_fields = ('whatsapp_link',)

@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'deposit_value', 'daily_gain', 'monthly_gain', 'cycle_days')
    search_fields = ('name',)

@admin.register(BankDetails)
class BankDetailsAdmin(admin.ModelAdmin):
    list_display = ('user', 'bank_name', 'account_holder_name')
    search_fields = ('user__phone_number', 'bank_name', 'account_holder_name')

@admin.register(PlatformBankDetails)
class PlatformBankDetailsAdmin(admin.ModelAdmin):
    list_display = ('bank_name', 'account_holder_name')
    search_fields = ('bank_name', 'account_holder_name')

@admin.register(Deposit)
class DepositAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'is_approved', 'created_at')
    search_fields = ('user__phone_number',)
    list_filter = ('is_approved',)

@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'status', 'created_at')
    search_fields = ('user__phone_number',)
    list_filter = ('status',)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('user', 'earnings', 'completed_at')
    search_fields = ('user__phone_number',)

@admin.register(Roulette)
class RouletteAdmin(admin.ModelAdmin):
    list_display = ('user', 'prize', 'is_approved', 'spin_date')
    search_fields = ('user__phone_number',)
    list_filter = ('is_approved',)

@admin.register(RouletteSettings)
class RouletteSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'prizes')

@admin.register(UserLevel)
class UserLevelAdmin(admin.ModelAdmin):
    list_display = ('user', 'level', 'purchase_date', 'is_active')
    search_fields = ('user__phone_number', 'level__name')
    list_filter = ('is_active',)
    
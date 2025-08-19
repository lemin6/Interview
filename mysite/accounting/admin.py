from django.contrib import admin
from django.contrib import messages
from django.urls import path
from django.shortcuts import redirect
from .models import BalanceArticle, BalanceGroup, Account, Transaction


@admin.register(BalanceArticle)
class BalanceArticleAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(BalanceGroup)
class BalanceGroupAdmin(admin.ModelAdmin):
    list_display = ("id", "article", "name")
    list_filter = ("article",)
    search_fields = ("name",)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "type", "group", "balance")
    list_filter = ("type", "group__article")
    search_fields = ("number", "name")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id", "created_at", "debit_account", "credit_account", "amount", "is_annulled", "reversal_of",
    )
    list_filter = ("is_annulled", "debit_account__group__article")
    search_fields = ("description",)
    readonly_fields = ("is_applied",)
    actions = ["make_annulled"]

    @admin.action(description="Аннулировать (сторно)")
    def make_annulled(self, request, queryset):
        count = 0
        for obj in queryset:
            try:
                obj.annul()
                count += 1
            except Exception as e:
                self.message_user(request, f"Не удалось аннулировать #{obj.pk}: {e}", level=messages.ERROR)
        if count:
            self.message_user(request, f"Аннулировано: {count}", level=messages.SUCCESS)
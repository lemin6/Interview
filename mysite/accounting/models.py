from __future__ import annotations
from decimal import Decimal
import random
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone


class BalanceArticle(models.Model):
    """Статья бухгалтерского баланса (верхний уровень)."""
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "Статья баланса"
        verbose_name_plural = "Статьи баланса"
        ordering = ["name"]

    def __str__(self):
        return self.name


class BalanceGroup(models.Model):
    """Балансовая группа (входит в статью)."""
    article = models.ForeignKey(
        BalanceArticle, on_delete=models.CASCADE, related_name="groups"
    )
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Балансовая группа"
        verbose_name_plural = "Балансовые группы"
        unique_together = ("article", "name")
        ordering = ["article__name", "name"]

    def __str__(self):
        return f"{self.article}: {self.name}"


class Account(models.Model):
    class AccountType(models.TextChoices):
        ASSET = "A", "Актив"
        LIABILITY = "P", "Пассив"
        BOTH = "AP", "Активно‑пассивный"

    def _generate_account_number() -> str:
        # 10 случайных цифр, проверяем уникальность
        while True:
            num = "".join(random.choices("0123456789", k=10))
            if not Account.objects.filter(number=num).exists():
                return num

    number = models.CharField(
        max_length=10,
        unique=True,
        default=_generate_account_number,
        help_text="Уникальный 10‑значный номер счёта",
    )
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=2, choices=AccountType.choices)
    group = models.ForeignKey(
        BalanceGroup, on_delete=models.PROTECT, related_name="accounts"
    )
    balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = "Счёт"
        verbose_name_plural = "Счета"
        ordering = ["number"]

    def __str__(self):
        return f"{self.number} — {self.name}"

    # Базовые правила двойной записи: для Актива дебет +, кредит −; для Пассивов наоборот.
    def apply_debit(self, amount: Decimal):
        if self.type in (Account.AccountType.ASSET, Account.AccountType.BOTH):
            self.balance += amount
        else:  # LIABILITY
            self.balance -= amount
        self.save(update_fields=["balance"])

    def apply_credit(self, amount: Decimal):
        if self.type in (Account.AccountType.ASSET, Account.AccountType.BOTH):
            self.balance -= amount
        else:  # LIABILITY
            self.balance += amount
        self.save(update_fields=["balance"])


class Transaction(models.Model):
    """Проводка по принципу двойной записи.

    Храним одну сумму (национальная валюта). Сумма по дебету = сумма по кредиту.
    При первом сохранении проводки баланс по задействованным счетам изменяется.
    """

    debit_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="debit_transactions", null=True, blank=True
    )
    credit_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="credit_transactions", null=True, blank=True
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Флаги для доп‑задания «сторно»
    is_annulled = models.BooleanField(default=False)
    reversal_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="reversals"
    )
    is_applied = models.BooleanField(default=False, help_text="Балансы уже изменены")

    class Meta:
        verbose_name = "Транзакция"
        verbose_name_plural = "Транзакции"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="amount_positive"),
        ]

    def __str__(self):
        return f"#{self.pk or '—'}: {self.debit_account} -> {self.credit_account} : {self.amount}"

    def clean(self):
        if self.debit_account_id is None or self.credit_account_id is None:
            raise ValidationError("Нужно выбрать оба счёта: дебет и кредит.")
        if self.debit_account_id == self.credit_account_id:
            raise ValidationError("Дебетовый и кредитовый счёт не могут совпадать.")
        if self.amount is None or self.amount <= 0:
            raise ValidationError("Сумма должна быть положительной.")

    def apply_balances(self):
        """Применить изменения к балансам по правилам двойной записи (идемпотентно)."""
        if self.is_applied:
            return
        with transaction.atomic():
            # Блокируем строки счетов до конца транзакции БД
            debit = Account.objects.select_for_update().get(pk=self.debit_account_id)
            credit = Account.objects.select_for_update().get(pk=self.credit_account_id)
            debit.apply_debit(self.amount)
            credit.apply_credit(self.amount)
            self.is_applied = True
            super(Transaction, self).save(update_fields=["is_applied"])  # только флаг

    def save(self, *args, **kwargs):
        # Валидируем перед сохранением
        self.full_clean()
        creating = self.pk is None
        super().save(*args, **kwargs)  # получаем pk для возможной ссылки
        # Применяем балансы ТОЛЬКО при первой фиксации обычной транзакции
        if creating and self.reversal_of_id is None:
            self.apply_balances()

    # === Доп. задание: «сторно» ===
    def annul(self) -> "Transaction":
        """Пометить как аннулированную и создать обратную транзакцию.
        Возвращает созданную сторно‑транзакцию.
        """
        if self.is_annulled:
            raise ValidationError("Транзакция уже аннулирована.")
        if self.reversal_of_id is not None:
            raise ValidationError("Нельзя аннулировать сторно‑транзакцию.")

        with transaction.atomic():
            # помечаем исходную
            self.is_annulled = True
            self.save(update_fields=["is_annulled"])  # без повторного применения балансов

            # создаём обратную (сразу применится при save -> apply_balances)
            reversal = Transaction.objects.create(
                debit_account=self.credit_account,
                credit_account=self.debit_account,
                amount=self.amount,
                description=f"Сторно транзакции #{self.pk}",
                reversal_of=self,
            )
            return reversal
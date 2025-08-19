from django import forms
from .models import Transaction


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["debit_account", "credit_account", "amount", "description"]

    def clean(self):
        cleaned = super().clean()
        debit = cleaned.get("debit_account")
        credit = cleaned.get("credit_account")
        amount = cleaned.get("amount")

        if not debit or not credit:
            raise forms.ValidationError("Выберите оба счёта: дебет и кредит.")
        if debit == credit:
            raise forms.ValidationError("Дебетовый и кредитовый счёт не могут совпадать.")
        if not amount or amount <= 0:
            raise forms.ValidationError("Сумма должна быть больше нуля.")

        return cleaned

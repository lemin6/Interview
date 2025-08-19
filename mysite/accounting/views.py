from django.shortcuts import render, redirect
from .models import Account, Transaction
from .forms import TransactionForm


def account_list(request):
    """Список счетов"""
    accounts = Account.objects.all()
    return render(request, "accounting/account_list.html", {"accounts": accounts})


def transaction_list(request):
    """История транзакций"""
    transactions = Transaction.objects.all().order_by("-created_at")
    return render(request, "accounting/transaction_list.html", {"transactions": transactions})


def transaction_create(request):
    """Создание транзакции"""
    if request.method == "POST":
        form = TransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)

            debit = transaction.debit_account
            credit = transaction.credit_account
            amount = transaction.amount

            # Логика двойной записи
            if debit.account_type == "asset" and credit.account_type == "asset":
                debit.balance += amount
                credit.balance -= amount
            elif debit.account_type == "liability" and credit.account_type == "liability":
                debit.balance -= amount
                credit.balance += amount
            elif debit.account_type == "asset" and credit.account_type == "liability":
                debit.balance += amount
                credit.balance += amount
            elif debit.account_type == "liability" and credit.account_type == "asset":
                debit.balance -= amount
                credit.balance -= amount

            debit.save()
            credit.save()
            transaction.save()

            return redirect("transaction_list")
    else:
        form = TransactionForm()

    return render(request, "accounting/transaction_form.html", {"form": form})

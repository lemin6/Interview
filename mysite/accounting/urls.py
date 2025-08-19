from django.urls import path
from . import views

urlpatterns = [
    path("accounts/", views.account_list, name="account_list"),
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("transactions/new/", views.transaction_create, name="transaction_create"),
]

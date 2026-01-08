from django.urls import path
from . import views

app_name = "articles"

urlpatterns = [
    path("", views.article_list, name="list"),            # public
    path("add/", views.article_create, name="add"),       # doctor only
    path("<int:pk>/edit/", views.article_edit, name="edit"),   # owner doctor only
    path("<int:pk>/delete/", views.article_delete, name="delete"), # owner doctor only
]

from django.urls import path

from wardrobe import views

app_name = "wardrobe"

urlpatterns = [
    path("", views.ClothingItemListView.as_view(), name="list"),
    path("add/", views.ClothingItemCreateView.as_view(), name="add"),
    path("<int:pk>/edit/", views.ClothingItemUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.ClothingItemDeleteView.as_view(), name="delete"),
]

from django.urls import path

from wardrobe import views

app_name = "wardrobe"

urlpatterns = [
    path("", views.ClothingItemListView.as_view(), name="list"),
]

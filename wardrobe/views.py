from django.views.generic import ListView

from wardrobe import models


class ClothingItemListView(ListView):
    model = models.ClothingItem
    context_object_name = "items"

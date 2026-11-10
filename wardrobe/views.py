from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from wardrobe import forms, models


class ClothingItemListView(ListView):
    model = models.ClothingItem
    context_object_name = "items"


# Create and update share wardrobe/clothingitem_form.html, the default
# template name for both views.
class ClothingItemCreateView(SuccessMessageMixin, CreateView):
    model = models.ClothingItem
    form_class = forms.ClothingItemForm
    success_url = reverse_lazy("wardrobe:list")
    success_message = "Item added."


class ClothingItemUpdateView(SuccessMessageMixin, UpdateView):
    model = models.ClothingItem
    form_class = forms.ClothingItemForm
    success_url = reverse_lazy("wardrobe:list")
    success_message = "Item updated."


# A GET shows the confirmation page; only the POST from it deletes.
class ClothingItemDeleteView(SuccessMessageMixin, DeleteView):
    model = models.ClothingItem
    success_url = reverse_lazy("wardrobe:list")
    success_message = "Item removed."

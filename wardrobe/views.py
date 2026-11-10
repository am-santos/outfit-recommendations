from typing import TYPE_CHECKING

from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from wardrobe import forms, models

# In django-stubs these classes take the model and the form as type parameters,
# but Django's own classes cannot be subscripted, so only mypy sees them.
if TYPE_CHECKING:
    from django.forms import ModelForm

    # The stubs accept only a model form as a DeleteView's form, although
    # Django's DeleteView uses a plain Form with no fields.
    _DeleteForm = ModelForm[models.ClothingItem]

    _ListView = ListView[models.ClothingItem]
    _CreateView = CreateView[models.ClothingItem, forms.ClothingItemForm]
    _UpdateView = UpdateView[models.ClothingItem, forms.ClothingItemForm]
    _DeleteView = DeleteView[models.ClothingItem, _DeleteForm]
    _SuccessMessageMixin = SuccessMessageMixin[forms.ClothingItemForm]
    _DeleteSuccessMessageMixin = SuccessMessageMixin[_DeleteForm]
else:
    _ListView = ListView
    _CreateView = CreateView
    _UpdateView = UpdateView
    _DeleteView = DeleteView
    _SuccessMessageMixin = SuccessMessageMixin
    _DeleteSuccessMessageMixin = SuccessMessageMixin


class ClothingItemListView(_ListView):
    model = models.ClothingItem
    context_object_name = "items"


# Create and update share wardrobe/clothingitem_form.html, the default
# template name for both views.
class ClothingItemCreateView(_SuccessMessageMixin, _CreateView):
    model = models.ClothingItem
    form_class = forms.ClothingItemForm
    success_url = reverse_lazy("wardrobe:list")
    success_message = "Item added."


class ClothingItemUpdateView(_SuccessMessageMixin, _UpdateView):
    model = models.ClothingItem
    form_class = forms.ClothingItemForm
    success_url = reverse_lazy("wardrobe:list")
    success_message = "Item updated."


# A GET shows the confirmation page; only the POST from it deletes.
class ClothingItemDeleteView(_DeleteSuccessMessageMixin, _DeleteView):
    model = models.ClothingItem
    success_url = reverse_lazy("wardrobe:list")
    success_message = "Item removed."

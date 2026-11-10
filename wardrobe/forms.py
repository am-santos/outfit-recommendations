from typing import TYPE_CHECKING

from django import forms

from wardrobe import models

# In django-stubs ModelForm takes the model as a type parameter, but Django's
# own class cannot be subscripted, so only mypy sees the parameter.
if TYPE_CHECKING:
    _ModelForm = forms.ModelForm[models.ClothingItem]
else:
    _ModelForm = forms.ModelForm


class ClothingItemForm(_ModelForm):
    class Meta:
        model = models.ClothingItem
        fields = [
            "name",
            "category",
            "colour",
            "size",
            "material",
            "warmth",
            "waterproof",
            "layerable",
        ]

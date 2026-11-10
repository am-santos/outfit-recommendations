from django import forms

from wardrobe import models


class ClothingItemForm(forms.ModelForm):
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

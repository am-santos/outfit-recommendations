from django.db import models


class ClothingItem(models.Model):
    class Category(models.TextChoices):
        TOP = "top", "Top"
        BOTTOM = "bottom", "Bottom"
        OUTER = "outer", "Outer layer"
        SHOES = "shoes", "Shoes"
        ACCESSORY = "accessory", "Accessory"

    class Material(models.TextChoices):
        COTTON = "cotton", "Cotton"
        WOOL = "wool", "Wool"
        DENIM = "denim", "Denim"
        LEATHER = "leather", "Leather"
        LINEN = "linen", "Linen"
        SYNTHETIC = "synthetic", "Synthetic"
        OTHER = "other", "Other"

    WARMTH_CHOICES = [
        (1, "1 – very light"),
        (2, "2"),
        (3, "3"),
        (4, "4"),
        (5, "5 – very warm"),
    ]

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=Category)
    colour = models.CharField(max_length=40)
    size = models.CharField(max_length=20, blank=True)
    material = models.CharField(max_length=20, choices=Material)
    warmth = models.PositiveSmallIntegerField(choices=WARMTH_CHOICES)
    waterproof = models.BooleanField(default=False)
    layerable = models.BooleanField(default=False)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return self.name

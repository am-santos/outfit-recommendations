from django.test import TestCase
from django.urls import reverse

from wardrobe import models


class ClothingItemModelTests(TestCase):
    def test_str_is_name(self):
        item = models.ClothingItem(name="Navy wool coat")
        self.assertEqual(str(item), "Navy wool coat")

    def test_ordered_by_category_then_name(self):
        for name, category in [
            ("Wool jumper", "top"),
            ("Belt", "accessory"),
            ("Boots", "shoes"),
            ("Jeans", "bottom"),
            ("Anorak", "outer"),
            ("Cotton shirt", "top"),
        ]:
            models.ClothingItem.objects.create(
                name=name,
                category=category,
                colour="Black",
                material="cotton",
                warmth=3,
            )
        names = [item.name for item in models.ClothingItem.objects.all()]
        # Categories sort by their stored values: accessory, bottom, outer, shoes, top.
        self.assertEqual(
            names, ["Belt", "Jeans", "Anorak", "Boots", "Cotton shirt", "Wool jumper"]
        )


class WardrobeListViewTests(TestCase):
    def test_empty_wardrobe_shows_message(self):
        response = self.client.get(reverse("wardrobe:list"))
        self.assertContains(response, "Your wardrobe is empty.")
        self.assertNotContains(response, "<table")

    def test_lists_items_with_attributes(self):
        models.ClothingItem.objects.create(
            name="Navy wool coat",
            category="outer",
            colour="Navy",
            size="M",
            material="wool",
            warmth=5,
            waterproof=True,
            layerable=False,
        )
        models.ClothingItem.objects.create(
            name="White T-shirt",
            category="top",
            colour="White",
            material="cotton",
            warmth=1,
            layerable=True,
        )
        response = self.client.get(reverse("wardrobe:list"))
        self.assertContains(
            response,
            '<th scope="col">Name</th><th scope="col">Category</th>'
            '<th scope="col">Colour</th><th scope="col">Size</th>'
            '<th scope="col">Material</th><th scope="col">Warmth</th>'
            '<th scope="col">Waterproof</th><th scope="col">Layerable</th>',
            html=True,
        )
        # Choices show their labels rather than the stored values, and the
        # booleans show Yes or No. A blank size leaves its cell empty.
        self.assertContains(
            response,
            '<th scope="row">Navy wool coat</th><td>Outer layer</td><td>Navy</td>'
            "<td>M</td><td>Wool</td><td>5 – very warm</td><td>Yes</td><td>No</td>",
            html=True,
        )
        self.assertContains(
            response,
            '<th scope="row">White T-shirt</th><td>Top</td><td>White</td>'
            "<td></td><td>Cotton</td><td>1 – very light</td><td>No</td><td>Yes</td>",
            html=True,
        )
        self.assertNotContains(response, "Your wardrobe is empty.")

    def test_url_name_maps_to_wardrobe_path(self):
        self.assertEqual(reverse("wardrobe:list"), "/wardrobe/")

    def test_page_uses_base_layout(self):
        response = self.client.get(reverse("wardrobe:list"))
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, '<html lang="en-GB">')
        self.assertContains(
            response, "<title>Wardrobe – What should I wear today?</title>", html=True
        )
        self.assertContains(response, '<a href="/wardrobe/">Wardrobe</a>', html=True)

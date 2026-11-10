from django.test import TestCase
from django.urls import reverse

from wardrobe import forms, models

FORM_FIELDS = [
    "name",
    "category",
    "colour",
    "size",
    "material",
    "warmth",
    "waterproof",
    "layerable",
]

# The add form filled in as a browser posts it: a ticked checkbox sends "on"
# and an unticked one is left out.
COAT_FORM_DATA = {
    "name": "Navy wool coat",
    "category": "outer",
    "colour": "Navy",
    "size": "M",
    "material": "wool",
    "warmth": "5",
    "waterproof": "on",
}


def create_coat() -> models.ClothingItem:
    return models.ClothingItem.objects.create(
        name="Navy wool coat",
        category="outer",
        colour="Navy",
        size="M",
        material="wool",
        warmth=5,
        waterproof=True,
    )


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

    def test_list_links_to_add_page(self):
        create_coat()
        response = self.client.get(reverse("wardrobe:list"))
        self.assertContains(
            response, f'<a href="{reverse("wardrobe:add")}">Add an item</a>', html=True
        )

    def test_empty_wardrobe_links_to_add_page(self):
        response = self.client.get(reverse("wardrobe:list"))
        self.assertContains(response, "Your wardrobe is empty.")
        self.assertContains(
            response, f'<a href="{reverse("wardrobe:add")}">Add an item</a>', html=True
        )

    def test_lists_edit_and_remove_links_per_item(self):
        coat = create_coat()
        shirt = models.ClothingItem.objects.create(
            name="White T-shirt",
            category="top",
            colour="White",
            material="cotton",
            warmth=1,
        )
        response = self.client.get(reverse("wardrobe:list"))
        self.assertContains(response, '<th scope="col">Actions</th>', html=True)
        for item in [coat, shirt]:
            with self.subTest(item=item.name):
                edit_url = reverse("wardrobe:edit", args=[item.pk])
                delete_url = reverse("wardrobe:delete", args=[item.pk])
                self.assertContains(
                    response,
                    f'<td><a href="{edit_url}">Edit</a>'
                    f'<a href="{delete_url}">Remove</a></td>',
                    html=True,
                )


class WardrobeCreateViewTests(TestCase):
    def test_url_is_wardrobe_add(self):
        self.assertEqual(reverse("wardrobe:add"), "/wardrobe/add/")

    def test_get_shows_form(self):
        response = self.client.get(reverse("wardrobe:add"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "wardrobe/clothingitem_form.html")
        form = response.context["form"]
        self.assertIsInstance(form, forms.ClothingItemForm)
        self.assertEqual(list(form.fields), FORM_FIELDS)
        self.assertContains(response, "<h1>Add an item</h1>", html=True)
        self.assertContains(response, '<form method="post">')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        for field in FORM_FIELDS:
            self.assertContains(response, f'name="{field}"')
        self.assertContains(response, '<a href="/wardrobe/">Cancel</a>', html=True)

    def test_post_creates_item_and_redirects(self):
        response = self.client.post(reverse("wardrobe:add"), COAT_FORM_DATA)
        self.assertRedirects(response, reverse("wardrobe:list"))
        self.assertEqual(
            models.ClothingItem.objects.values(*FORM_FIELDS).get(),
            {
                "name": "Navy wool coat",
                "category": "outer",
                "colour": "Navy",
                "size": "M",
                "material": "wool",
                "warmth": 5,
                "waterproof": True,
                "layerable": False,
            },
        )

    def test_post_rejects_warmth_out_of_range(self):
        for warmth in ["0", "6"]:
            with self.subTest(warmth=warmth):
                response = self.client.post(
                    reverse("wardrobe:add"), {**COAT_FORM_DATA, "warmth": warmth}
                )
                self.assertEqual(response.status_code, 200)
                self.assertFormError(
                    response.context["form"],
                    "warmth",
                    f"Select a valid choice. {warmth} is not one of the available "
                    "choices.",
                )
                self.assertFalse(models.ClothingItem.objects.exists())

    def test_shows_item_added_message(self):
        response = self.client.post(
            reverse("wardrobe:add"), COAT_FORM_DATA, follow=True
        )
        self.assertContains(
            response, '<ul class="messages"><li>Item added.</li></ul>', html=True
        )


class WardrobeUpdateViewTests(TestCase):
    item: models.ClothingItem

    @classmethod
    def setUpTestData(cls):
        cls.item = create_coat()

    def test_url_is_wardrobe_pk_edit(self):
        self.assertEqual(reverse("wardrobe:edit", args=[7]), "/wardrobe/7/edit/")

    def test_get_shows_form_with_current_values(self):
        response = self.client.get(reverse("wardrobe:edit", args=[self.item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "wardrobe/clothingitem_form.html")
        form = response.context["form"]
        self.assertIsInstance(form, forms.ClothingItemForm)
        self.assertEqual(form.instance, self.item)
        self.assertContains(response, "<h1>Edit item</h1>", html=True)
        self.assertContains(response, 'value="Navy wool coat"')
        self.assertContains(
            response, '<option value="outer" selected>Outer layer</option>', html=True
        )
        self.assertContains(
            response, '<option value="5" selected>5 – very warm</option>', html=True
        )
        self.assertContains(
            response,
            '<input type="checkbox" name="waterproof" id="id_waterproof" checked>',
            html=True,
        )
        self.assertContains(response, '<a href="/wardrobe/">Cancel</a>', html=True)

    def test_post_updates_item(self):
        response = self.client.post(
            reverse("wardrobe:edit", args=[self.item.pk]),
            {
                "name": "Navy wool overcoat",
                "category": "outer",
                "colour": "Dark navy",
                "size": "L",
                "material": "wool",
                "warmth": "4",
                "layerable": "on",
            },
        )
        self.assertRedirects(response, reverse("wardrobe:list"))
        # The same item changed in place; unticking waterproof saved False.
        self.assertEqual(
            models.ClothingItem.objects.values("pk", *FORM_FIELDS).get(),
            {
                "pk": self.item.pk,
                "name": "Navy wool overcoat",
                "category": "outer",
                "colour": "Dark navy",
                "size": "L",
                "material": "wool",
                "warmth": 4,
                "waterproof": False,
                "layerable": True,
            },
        )

    def test_post_rejects_invalid_data_and_keeps_item(self):
        stored = models.ClothingItem.objects.values(*FORM_FIELDS).get()
        response = self.client.post(
            reverse("wardrobe:edit", args=[self.item.pk]),
            {**COAT_FORM_DATA, "name": "Navy wool overcoat", "warmth": "6"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "warmth",
            "Select a valid choice. 6 is not one of the available choices.",
        )
        # The form comes back as the edit page, and nothing is saved, not even
        # the valid change of name.
        self.assertContains(response, "<h1>Edit item</h1>", html=True)
        self.assertEqual(models.ClothingItem.objects.values(*FORM_FIELDS).get(), stored)

    def test_shows_item_updated_message(self):
        response = self.client.post(
            reverse("wardrobe:edit", args=[self.item.pk]), COAT_FORM_DATA, follow=True
        )
        self.assertContains(
            response, '<ul class="messages"><li>Item updated.</li></ul>', html=True
        )

    def test_unknown_item_returns_404(self):
        url = reverse("wardrobe:edit", args=[self.item.pk + 1])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, COAT_FORM_DATA).status_code, 404)
        self.assertEqual(models.ClothingItem.objects.count(), 1)


class WardrobeDeleteViewTests(TestCase):
    item: models.ClothingItem

    @classmethod
    def setUpTestData(cls):
        cls.item = create_coat()

    def test_url_is_wardrobe_pk_delete(self):
        self.assertEqual(reverse("wardrobe:delete", args=[7]), "/wardrobe/7/delete/")

    def test_get_shows_confirmation(self):
        response = self.client.get(reverse("wardrobe:delete", args=[self.item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "wardrobe/clothingitem_confirm_delete.html")
        self.assertContains(
            response, "<p>Remove Navy wool coat from your wardrobe?</p>", html=True
        )
        self.assertContains(
            response, '<button type="submit">Remove</button>', html=True
        )
        self.assertContains(response, '<a href="/wardrobe/">Cancel</a>', html=True)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        # Showing the page deletes nothing; only the POST from it does.
        self.assertTrue(models.ClothingItem.objects.filter(pk=self.item.pk).exists())

    def test_post_deletes_item_and_redirects(self):
        response = self.client.post(reverse("wardrobe:delete", args=[self.item.pk]))
        self.assertRedirects(response, reverse("wardrobe:list"))
        self.assertFalse(models.ClothingItem.objects.filter(pk=self.item.pk).exists())

    def test_shows_item_removed_message(self):
        response = self.client.post(
            reverse("wardrobe:delete", args=[self.item.pk]), follow=True
        )
        self.assertContains(
            response, '<ul class="messages"><li>Item removed.</li></ul>', html=True
        )

    def test_unknown_item_returns_404(self):
        url = reverse("wardrobe:delete", args=[self.item.pk + 1])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertTrue(models.ClothingItem.objects.filter(pk=self.item.pk).exists())

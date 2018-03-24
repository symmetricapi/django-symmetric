from django.conf import settings
from django.db import models
from django.test import TestCase

from symmetric.filters import subclass_filter
from symmetric.functions import datetime_to_iso_8601, get_object_list_data


class Place(models.Model):
    name = models.CharField(max_length=127)
    website = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    attributes = models.IntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)


class Restaurant(Place):
    seating_capacity = models.IntegerField()
    average_rating = models.FloatField()
    cuisine = models.CharField(max_length=127)


class Store(Place):
    type = models.IntegerField()
    average_price = models.FloatField()


def fake_request():
    pass


class ApiSubclassFilterTest(TestCase):

    def setUp(self):
        self.restaurant = Restaurant.objects.create(
            name='Tasty Meals',
            website='tastymeals.com',
            attributes=16,
            seating_capacity=35,
            average_rating=4.6,
            cuisine='Good Food'
        )
        self.store = Store.objects.create(
            name='Sneaker Shoppe',
            website='sneakershoppe.com',
            attributes=10,
            type=2,
            average_price=67.90
        )

    def test_subclass_filter(self):
        queryset_filter = subclass_filter(Restaurant, Store)
        queryset = queryset_filter(fake_request, Place.objects.all())
        for place in queryset:
            self.assertTrue(isinstance(place, (Restaurant, Store)))
            data = get_object_list_data(place)
            if place.id == self.restaurant.id:
                obj = self.restaurant
                self.assertEqual(obj.seating_capacity, data['seatingCapacity'])
                self.assertEqual(obj.average_rating, data['averageRating'])
                self.assertEqual(obj.cuisine, data['cuisine'])
            if place.id == self.store.id:
                obj = self.store
                self.assertEqual(obj.type, data['type'])
                self.assertEqual(obj.average_price, data['averagePrice'])
            self.assertEqual(obj.name, data['name'])
            self.assertEqual(obj.website, data['website'])
            self.assertEqual(obj.description, data['description'])
            self.assertEqual(obj.attributes, data['attributes'])
            self.assertEqual(datetime_to_iso_8601(obj.created), data['created'])

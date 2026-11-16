from django.db import models


class Moneda(models.TextChoices):
    ARS = "ARS", "Pesos argentinos"
    USD = "USD", "Dólares estadounidenses"

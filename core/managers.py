# core/managers.py  ---- custom queryset manager 
from django.db import models
class OwnedQuerySet(models.QuerySet):
    def for_user(self, user): return self.filter(user=user)
from django.core.management.base import BaseCommand
from core.models import Currency

class Command(BaseCommand):
    help = "Abuur currencies USD iyo SOS haddii aysan jirin"

    def handle(self, *args, **kwargs):
        currencies = [
            {"code": "USD", "name": "US Dollar"},
            {"code": "SOS", "name": "Somali Shilling"},
        ]

        for cur in currencies:
            obj, created = Currency.objects.get_or_create(
                code=cur["code"], defaults={"name": cur["name"]}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Currency '{cur['code']}' la abuuray"))
            else:
                self.stdout.write(f"Currency '{cur['code']}' hore ayaa loo abuuray")

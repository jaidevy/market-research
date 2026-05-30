from django.core.management.base import BaseCommand

from services.runtime.workflow_templates import seed_generic_workflow_assets


class Command(BaseCommand):
    help = "Seed generic workflow templates, agents, skills, and tools."

    def handle(self, *args, **options):
        seeded = seed_generic_workflow_assets()
        templates = seeded.get("templates") or []
        self.stdout.write(self.style.SUCCESS(
            "Seeded {tools} tools, {skills} skills, {agents} agents, and {templates} workflow templates.".format(
                tools=seeded.get("tools", 0),
                skills=seeded.get("skills", 0),
                agents=seeded.get("agents", 0),
                templates=len(templates),
            )
        ))
        for template in templates:
            self.stdout.write(f"- {template.name}")

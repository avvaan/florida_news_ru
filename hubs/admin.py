from django.contrib import admin

from core.i18n import uk_fieldset

from .models import Program


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "changed_on", "checked_on", "is_published", "order")
    list_editable = ("status", "is_published", "order")
    list_filter = ("status", "is_published")
    search_fields = ("title", "summary", "sources", "editor_note")
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        (None, {"fields": ("title", "slug", "status", "summary", "what_to_do", "sources", "guide_slug")}),
        ("Даты и показ", {"fields": ("changed_on", "checked_on", "order", "is_published", "editor_note"),
                          "description": "Поменяли статус или текст — обновите «проверено редакцией»: дата видна "
                                         "читателям."}),
        uk_fieldset(Program),
    )

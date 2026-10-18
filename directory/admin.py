from django.contrib import admin

from django.contrib import messages

from . import moderation
from .models import Category, Listing, Submission


class ListingInline(admin.TabularInline):
    model = Listing
    extra = 0
    fields = ("name", "url", "city", "is_recommended", "is_partner", "is_active", "order")
    show_change_link = True


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "n_listings", "order")
    list_filter = ("kind",)
    list_editable = ("order",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ListingInline]

    @admin.display(description="записей")
    def n_listings(self, obj):
        return obj.listings.filter(is_active=True).count()


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "city", "is_recommended", "is_partner", "from_owner", "is_active", "updated_at")
    list_filter = ("category__kind", "category", "is_recommended", "is_partner", "from_owner", "is_active", "region")
    list_editable = ("is_recommended", "is_partner", "is_active")
    search_fields = ("name", "description", "city", "address", "editor_note")
    fieldsets = (
        (None, {"fields": ("category", "name", "description", "url", "phone")}),
        ("Где и когда", {"fields": ("address", "city", "region", "hours", "languages")}),
        ("Показ", {"fields": ("is_recommended", "is_partner", "is_active", "order", "guide_slug", "from_owner", "editor_note"),
                   "description": "Платное размещение обязательно отмечайте «партнёр»: читатели видят метку."}),
    )


@admin.action(description="Проверить ИИ ещё раз (только «на проверке»)")
def action_remoderate(modeladmin, request, queryset):
    done = sum(moderation.moderate(sub).status != Submission.Status.PENDING
               for sub in queryset.filter(status=Submission.Status.PENDING))
    modeladmin.message_user(request, f"Проверено заявок: {done}", messages.SUCCESS)


@admin.action(description="Снять с публикации и отклонить")
def action_reject(modeladmin, request, queryset):
    for sub in queryset:
        if sub.listing_id:
            Listing.objects.filter(pk=sub.listing_id).update(is_active=False)
        moderation.reject(sub, "other", f"Отклонено редакцией ({request.user})")
    modeladmin.message_user(request, "Отклонено", messages.WARNING)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "name", "category", "city", "status", "violation", "listing", "contact_email")
    list_filter = ("status", "violation", "category")
    search_fields = ("name", "description", "contact_email", "contact_name", "phone", "url")
    date_hierarchy = "created_at"
    actions = [action_remoderate, action_reject]
    readonly_fields = [f.name for f in Submission._meta.fields]

    def has_add_permission(self, request):
        return False

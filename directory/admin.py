from django.contrib import admin

from .models import Category, Listing


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
    list_display = ("name", "category", "city", "is_recommended", "is_partner", "is_active", "updated_at")
    list_filter = ("category__kind", "category", "is_recommended", "is_partner", "is_active", "region")
    list_editable = ("is_recommended", "is_partner", "is_active")
    search_fields = ("name", "description", "city", "address")
    fieldsets = (
        (None, {"fields": ("category", "name", "description", "url", "phone")}),
        ("Где и когда", {"fields": ("address", "city", "region", "hours", "languages")}),
        ("Показ", {"fields": ("is_recommended", "is_partner", "is_active", "order", "guide_slug"),
                   "description": "Платное размещение обязательно отмечайте «партнёр»: читатели видят метку."}),
    )

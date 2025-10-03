from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CompteUser

class CompteUserAdmin(UserAdmin):
    list_display = ('email', 'nom', 'prenom', 'type_compte', 'departement', 'is_active')
    list_filter = ('type_compte', 'departement', 'is_active')
    search_fields = ('email', 'nom', 'prenom')
    ordering = ('email',)  # Utiliser email au lieu de username
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Informations personnelles', {'fields': ('nom', 'prenom', 'telephone', 'date_naissance', 'photo')}),
        ('Informations professionnelles', {'fields': ('type_compte', 'fonction', 'departement')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates importantes', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'nom', 'prenom', 'password1', 'password2'),
        }),
    )

admin.site.register(CompteUser, CompteUserAdmin)
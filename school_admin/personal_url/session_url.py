from django.urls import path
from ..personal_views.session_view import *

app_name = 'session'

urlpatterns = [
    path('changer/', changer_session, name='changer_session'),
    path('info/', session_active_info, name='session_active_info'),
]


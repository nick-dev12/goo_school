from django.templatetags.static import static


class ContextPopupMiddleware:
    dashboards = {'dashboard_directeur', 'dashboard_enseignant', 'dashboard', 'dashboard_parent',
                  'dashboard_eleve', 'dashboard_secretaire', 'dashboard_personnel_administratif',
                  'dashboard_comptable', 'dashboard_administrateur_etablissement'}
    roles = {'etablissement', 'professeur', 'parent', 'eleve', 'personneladministratif'}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, 'resolver_match', None)
        user = getattr(request, 'user', None)
        excluded = ('/api/', '/connexion', '/deconnexion', '/password', '/auth/', '/static/', '/media/')
        if (match and request.method == 'GET' and not request.path.startswith(excluded)
                and not any(word in (match.url_name or '') for word in ('imprimer', 'recu', 'pdf', 'export'))
                and user and user.is_authenticated
                and user._meta.model_name in self.roles and response.status_code == 200
                and not response.streaming and 'text/html' in response.get('Content-Type', '')
                and not request.headers.get('X-Requested-With')):
            marker = b'</body>'
            if marker in response.content:
                script = f'<script type="module" src="{static("school_admin/js/shared/context_popups.js")}?v=8"></script>'
                response.content = response.content.replace(marker, script.encode() + marker, 1)
                if response.has_header('Content-Length'):
                    response['Content-Length'] = str(len(response.content))
        return response

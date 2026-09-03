import 'package:flutter/material.dart';

/// Textes courts affichés dans les popups système (Info.plist / Android).
class PermissionPurposeStrings {
  static const cameraSystem =
      'Scanner votre QR code de connexion (carte élève ou étudiant), prendre une photo d\'identité scolaire ou joindre un document.';

  static const microphoneSystem =
      'Activer le son pour un cours en ligne ou un message vocal sur Aria-edu.';

  static const photoLibrarySystem =
      'Choisir une photo de profil, d\'identité ou un document à envoyer sur Aria-edu.';

  static const photoLibraryAddSystem =
      'Enregistrer un bulletin ou une attestation téléchargée depuis Aria-edu.';

  static const locationSystem =
      'Confirmer une présence à l\'école lors d\'un pointage activé par votre établissement.';

  static const notificationSystem =
      'Recevoir les alertes scolaires (devoirs, messages, absences) sur Aria-edu.';
}

/// Dialogue in-app avant la popup système (surtout utile sur Android WebView).
Future<bool> showPermissionRationaleDialog({
  required BuildContext context,
  required String title,
  required String message,
}) async {
  final result = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Refuser'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text('Continuer'),
        ),
      ],
    ),
  );
  return result ?? false;
}

String? webViewPermissionTitle(List<dynamic> resources) {
  final names = resources.map((r) => r.toString().toLowerCase()).join(' ');
  if (names.contains('camera')) {
    return 'Accès à la caméra';
  }
  if (names.contains('microphone') || names.contains('audio')) {
    return 'Accès au microphone';
  }
  if (names.contains('protected_media') || names.contains('video')) {
    return 'Accès caméra et son';
  }
  return null;
}

String? webViewPermissionMessage(List<dynamic> resources) {
  final names = resources.map((r) => r.toString().toLowerCase()).join(' ');
  final needsCamera = names.contains('camera');
  final needsMic =
      names.contains('microphone') || names.contains('audio');

  if (needsCamera && needsMic) {
    return 'Aria-edu a besoin de la caméra et du microphone pour le scan QR, la photo d\'identité ou un cours en ligne.';
  }
  if (needsCamera) {
    return PermissionPurposeStrings.cameraSystem;
  }
  if (needsMic) {
    return PermissionPurposeStrings.microphoneSystem;
  }
  return null;
}

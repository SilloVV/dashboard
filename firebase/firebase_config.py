# firebase_config.py - Version simple
import firebase_admin
from firebase_admin import credentials, firestore
import os
from pathlib import Path

def initialize_firebase():
    """Initialise Firebase en trouvant automatiquement le fichier de clés"""
    
    if firebase_admin._apps:
        return firestore.client()
    
    # Chemin relatif depuis ce fichier (firebase_config.py)
    current_file = Path(__file__)
    key_path = current_file.parent / "serviceAccountKey.json"
    
    # Vérifier que le fichier existe
    if not key_path.exists():
        raise FileNotFoundError(
            f"Fichier non trouvé: {key_path}\n"
            f"Assure-toi que serviceAccountKey.json est dans le dossier firebase/"
        )
    
    # Initialiser Firebase
    cred = credentials.Certificate(str(key_path))
    firebase_admin.initialize_app(cred)
    
    print(f"🔥 Firebase initialisé!")

    return firestore.client()

# Instance globale du client Firestore
db = initialize_firebase()
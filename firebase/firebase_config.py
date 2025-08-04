# firebase_config.py - Version Streamlit Cloud
import firebase_admin
from firebase_admin import credentials, firestore
import os
import streamlit as st
from pathlib import Path

def initialize_firebase():
    """Initialise Firebase avec support Streamlit Cloud et développement local"""
    
    if firebase_admin._apps:
        return firestore.client()
    
    try:
        # Essayer d'abord les secrets Streamlit Cloud
        firebase_config = dict(st.secrets['firebase'])
        cred = credentials.Certificate(firebase_config)
        firebase_admin.initialize_app(cred)
        print("🔥 Firebase initialisé via Streamlit Cloud secrets!")
        
    except (KeyError, AttributeError, FileNotFoundError):
        # Fallback vers le fichier local
        current_file = Path(__file__)
        key_path = current_file.parent / "serviceAccountKey.json"
        
        if not key_path.exists():
            raise FileNotFoundError(
                f"Configuration Firebase manquante.\n"
                f"Pour Streamlit Cloud: ajoutez la section [firebase] dans les secrets\n"
                f"Pour le développement local: placez serviceAccountKey.json dans firebase/\n"
                f"Consultez STREAMLIT_CLOUD_SETUP.md pour plus d'infos"
            )
        
        cred = credentials.Certificate(str(key_path))
        firebase_admin.initialize_app(cred)
        print("🔥 Firebase initialisé en local!")

    return firestore.client()

# Instance globale du client Firestore
db = initialize_firebase()
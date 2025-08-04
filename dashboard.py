import streamlit as st
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from collections import defaultdict, Counter

# Configuration du chemin pour les imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import Firebase
try:
    from firebase.firebase_config import db
    print("✅ Firebase configuré avec succès")
except ImportError as e:
    print(f"❌ Erreur import Firebase: {e}")
    db = None

def init_firebase():
    """Initialise la connexion Firebase"""
    try:
        if not db:
            st.error("❌ Firebase non disponible. Vérifiez la configuration.")
            return None
        return db
    except Exception as e:
        st.error(f"❌ Erreur de connexion Firebase: {e}")
        return None

@st.cache_data(ttl=60)  # Cache pendant 1 minute
def load_conversations_from_firebase():
    """
    Charge toutes les conversations depuis Firebase avec cache
    """
    firestore_db = init_firebase()
    if not firestore_db:
        return []
    
    conversations = []
    
    try:
        # Récupérer toutes les conversations
        conversations_ref = firestore_db.collection('conversations')
        conversation_docs = conversations_ref.get()
        
        for conv_doc in conversation_docs:
            conv_id = conv_doc.id
            conv_data = conv_doc.to_dict()
            
            # Récupérer les métadonnées
            metadata = conv_data.get('metadata', {})
            
            # Récupérer tous les messages de cette conversation
            messages_ref = conversations_ref.document(conv_id).collection('messages')
            message_docs = messages_ref.get()
            
            messages = []
            for msg_doc in message_docs:
                msg_data = msg_doc.to_dict()
                msg_data['id'] = msg_doc.id
                
                # Convertir timestamp Firebase en datetime si nécessaire
                if 'timestamp' in msg_data and hasattr(msg_data['timestamp'], 'timestamp'):
                    msg_data['timestamp'] = msg_data['timestamp'].timestamp()
                
                messages.append(msg_data)
            
            # Trier les messages par timestamp
            messages.sort(key=lambda x: x.get('timestamp', 0))
            
            conversations.append({
                'id': conv_id,
                'metadata': metadata,
                'messages': messages
            })
        
        return conversations
        
    except Exception as e:
        st.error(f"❌ Erreur lors du chargement des conversations: {e}")
        return []

def delete_duplicate_questions_from_firebase():
    """
    Supprime les questions en doublon directement de Firebase
    Retourne le nombre de doublons supprimés
    """
    firestore_db = init_firebase()
    if not firestore_db:
        return 0
    
    deleted_count = 0
    seen_questions = set()
    
    try:
        st.info("🔄 Analyse des conversations pour identifier les doublons...")
        conversations_ref = firestore_db.collection('conversations')
        conversation_docs = conversations_ref.get()
        
        messages_to_delete = []
        
        for conv_doc in conversation_docs:
            conv_id = conv_doc.id
            messages_ref = conversations_ref.document(conv_id).collection('messages')
            message_docs = messages_ref.get()
            
            for msg_doc in message_docs:
                msg_data = msg_doc.to_dict()
                question = msg_data.get('question', '').strip().lower()
                
                if question:
                    if question in seen_questions:
                        # Question en doublon - la marquer pour suppression
                        messages_to_delete.append({
                            'conv_id': conv_id,
                            'msg_id': msg_doc.id,
                            'question': question
                        })
                    else:
                        seen_questions.add(question)
        
        # Supprimer les messages en doublon
        if messages_to_delete:
            progress_bar = st.progress(0)
            for i, msg_info in enumerate(messages_to_delete):
                try:
                    conversations_ref.document(msg_info['conv_id']).collection('messages').document(msg_info['msg_id']).delete()
                    deleted_count += 1
                    progress_bar.progress((i + 1) / len(messages_to_delete))
                except Exception as e:
                    st.error(f"Erreur lors de la suppression du message {msg_info['msg_id']}: {e}")
            
            progress_bar.empty()
            st.success(f"✅ {deleted_count} questions en doublon supprimées de Firebase")
        else:
            st.info("✅ Aucun doublon trouvé dans la base de données")
            
    except Exception as e:
        st.error(f"❌ Erreur lors de la suppression des doublons: {e}")
    
    return deleted_count

def get_available_emails():
    """
    Récupère la liste des emails uniques depuis la collection users (sans doublons)
    """
    firestore_db = init_firebase()
    if not firestore_db:
        return []
    
    emails = []
    
    try:
        # Récupérer tous les utilisateurs depuis la collection users
        users_ref = firestore_db.collection('users')
        user_docs = users_ref.get()
        
        for user_doc in user_docs:
            user_data = user_doc.to_dict()
            email = user_data.get('email', '')
            
            if email:
                emails.append(email)
        
        return sorted(emails)  # Retourner une liste triée
        
    except Exception as e:
        st.error(f"❌ Erreur lors du chargement des emails: {e}")
        return []

def get_email_connection_stats():
    """
    Récupère les statistiques de connexion des emails depuis la collection users
    """
    firestore_db = init_firebase()
    if not firestore_db:
        return []
    
    email_stats = []
    
    try:
        # Récupérer tous les utilisateurs depuis la collection users
        users_ref = firestore_db.collection('users')
        user_docs = users_ref.get()
        
        for user_doc in user_docs:
            user_data = user_doc.to_dict()
            email = user_data.get('email', '')
            
            if email and email != "admin@chatbot":  # Exclure l'admin factice
                total_connections = user_data.get('total_connections', 0)
                last_connection = user_data.get('last_connection', None)
                
                # Formater la dernière connexion
                if last_connection:
                    if hasattr(last_connection, 'timestamp'):
                        last_connection_str = datetime.fromtimestamp(last_connection.timestamp()).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        last_connection_str = str(last_connection)[:19]  # Prendre les 19 premiers caractères
                else:
                    last_connection_str = "Jamais"
                
                email_stats.append({
                    'email': email,
                    'total_connections': total_connections,
                    'last_connection': last_connection_str,
                    'last_connection_raw': last_connection
                })
        
        # Trier par nombre de connexions décroissant
        email_stats = sorted(email_stats, key=lambda x: x['total_connections'], reverse=True)
        
        return email_stats
        
    except Exception as e:
        st.error(f"❌ Erreur lors du chargement des statistiques d'emails: {e}")
        return []

def get_conversations_by_user_email(user_email: str = None):
    """
    Récupère les conversations associées à un email utilisateur spécifique
    Si user_email est None, retourne toutes les conversations avec leur email associé
    """
    firestore_db = init_firebase()
    if not firestore_db:
        return []
    
    conversations_with_email = []
    
    try:
        # Récupérer toutes les conversations
        conversations_ref = firestore_db.collection('conversations')
        conversation_docs = conversations_ref.get()
        
        for conv_doc in conversation_docs:
            conv_id = conv_doc.id
            conv_data = conv_doc.to_dict()
            
            # Récupérer l'email depuis les métadonnées de la conversation
            conversation_metadata = conv_data.get('metadata', {})
            conv_user_email = conversation_metadata.get('email', '')
            
            # Si un email spécifique est demandé, filtrer
            if user_email and conv_user_email.lower() != user_email.lower():
                continue
            
            # Récupérer les messages de cette conversation
            messages_ref = conversations_ref.document(conv_id).collection('messages')
            message_docs = messages_ref.get()
            
            messages = []
            for msg_doc in message_docs:
                msg_data = msg_doc.to_dict()
                msg_data['id'] = msg_doc.id
                
                # Convertir timestamp Firebase en datetime si nécessaire
                if 'timestamp' in msg_data and hasattr(msg_data['timestamp'], 'timestamp'):
                    msg_data['timestamp'] = msg_data['timestamp'].timestamp()
                
                messages.append(msg_data)
            
            # Trier les messages par timestamp
            messages.sort(key=lambda x: x.get('timestamp', 0))
            
            conversations_with_email.append({
                'id': conv_id,
                'email': conv_user_email,
                'metadata': conversation_metadata,
                'messages': messages,
                'message_count': len(messages),
                'created_at': conversation_metadata.get('created_at'),
                'last_updated': conversation_metadata.get('last_updated')
            })
        
        # Trier par date de création décroissante
        conversations_with_email.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
        
        return conversations_with_email
        
    except Exception as e:
        st.error(f"❌ Erreur lors du chargement des conversations par email: {e}")
        return []


def match_email_pattern(email, pattern):
    """
    Vérifie si un email correspond à un pattern
    Patterns supportés:
    - @domain.com : emails se terminant par ce domaine
    - user@* : emails commençant par ce préfixe
    - *@domain.com : emails avec ce domaine
    - email exact
    - substring simple
    """
    if not pattern:
        return True
    
    if not email:
        return False
    
    # Normalisation (au cas où ce ne serait pas déjà fait)
    pattern = pattern.strip().lower()
    email = email.strip().lower()
    
    # Debug
    print(f"DEBUG match_email_pattern: email='{email}', pattern='{pattern}'")
    
    # Pattern exacte
    if pattern == email:
        print(f"DEBUG: Exact match found")
        return True
    
    # Pattern domaine: @domain.com
    if pattern.startswith('@'):
        result = email.endswith(pattern)
        print(f"DEBUG: Domain pattern '@...' - result: {result}")
        return result
    
    # Pattern préfixe: user@*
    if pattern.endswith('@*'):
        prefix = pattern[:-2]  # Enlever @*
        result = email.startswith(prefix + '@')
        print(f"DEBUG: Prefix pattern 'user@*' - checking prefix '{prefix}@' - result: {result}")
        return result
    
    # Pattern domaine avec wildcard: *@domain.com
    if pattern.startswith('*@'):
        domain = pattern[1:]  # Enlever *
        result = email.endswith(domain)
        print(f"DEBUG: Wildcard domain pattern '*@...' - checking domain '{domain}' - result: {result}")
        return result
    
    # Pattern avec wildcards multiples
    if '*' in pattern:
        # Convertir pattern en regex simple
        import re
        # Échapper les caractères spéciaux sauf *
        escaped_pattern = re.escape(pattern).replace('\\*', '.*')
        regex_pattern = f'^{escaped_pattern}$'
        result = bool(re.match(regex_pattern, email))
        print(f"DEBUG: Wildcard pattern - regex: '{regex_pattern}' - result: {result}")
        return result
    
    # Pattern contient (substring)
    result = pattern in email
    print(f"DEBUG: Substring pattern - result: {result}")
    return result

def filter_conversations(conversations, date_filter="Toutes", user_filter="Tous les utilisateurs", specific_email="", precise_date=None, email_pattern=""):
    """
    Filtre les conversations selon les critères sélectionnés
    """
    if not conversations:
        return [], {}
    
    # Filtrage par date
    filtered_conversations = conversations.copy()
    
    # Filtrage par date précise
    if precise_date is not None:
        from datetime import datetime, timedelta
        
        # Convertir la date précise en range (toute la journée)
        start_date = datetime.combine(precise_date, datetime.min.time())
        end_date = datetime.combine(precise_date, datetime.max.time())
        
        filtered_conversations = []
        for conv in conversations:
            conv_date = None
            messages = conv.get('messages', [])
            if messages:
                # Prendre le timestamp du premier message
                first_msg = messages[0]
                if 'timestamp' in first_msg:
                    if hasattr(first_msg['timestamp'], 'timestamp'):
                        conv_date = datetime.fromtimestamp(first_msg['timestamp'].timestamp())
                    else:
                        conv_date = datetime.fromtimestamp(first_msg['timestamp'])
            
            if conv_date and start_date <= conv_date <= end_date:
                filtered_conversations.append(conv)
    
    # Filtrage par période relative (si pas de date précise)
    elif date_filter != "Toutes":
        from datetime import datetime, timedelta
        
        days = {"7 derniers jours": 7, "30 derniers jours": 30, "90 derniers jours": 90}
        cutoff_date = datetime.now() - timedelta(days=days[date_filter])
        
        filtered_conversations = []
        for conv in conversations:
            conv_date = None
            messages = conv.get('messages', [])
            if messages:
                # Prendre le timestamp du premier message
                first_msg = messages[0]
                if 'timestamp' in first_msg:
                    if hasattr(first_msg['timestamp'], 'timestamp'):
                        conv_date = datetime.fromtimestamp(first_msg['timestamp'].timestamp())
                    else:
                        conv_date = datetime.fromtimestamp(first_msg['timestamp'])
            
            if conv_date and conv_date >= cutoff_date:
                filtered_conversations.append(conv)
    
    # Filtrage par utilisateur et calcul des statistiques
    admin_questions = 0
    user_questions = 0
    total_questions = 0
    
    final_conversations = []
    
    for conv in filtered_conversations:
        messages = conv.get('messages', [])
        filtered_messages = []
        
        for msg in messages:
            if msg.get('question', '').strip():
                msg_user_id = msg.get('metadata', {}).get('user_id', 1)
                
                # Compter toutes les questions pour les stats
                total_questions += 1
                if msg_user_id == 0:
                    admin_questions += 1
                else:
                    user_questions += 1
                
                # Récupérer l'email depuis les métadonnées du message (multiple fallbacks)
                msg_email = msg.get('metadata', {}).get('user_info', {}).get('user_email', '')
                if not msg_email:
                    # Fallback 1: direct email in metadata
                    msg_email = msg.get('metadata', {}).get('email', '')
                if not msg_email:
                    # Fallback 2: user_info without nested user_email
                    user_info = msg.get('metadata', {}).get('user_info', {})
                    if isinstance(user_info, dict):
                        msg_email = user_info.get('email', '')
                
                # Normaliser l'email (strip whitespace and lowercase for comparison)
                msg_email = msg_email.strip().lower() if msg_email else ''
                
                # Debug: log structure of metadata for debugging
                if st.session_state.get('debug_email_filter', False):
                    st.write(f"DEBUG: Message metadata structure: {msg.get('metadata', {})}")
                    st.write(f"DEBUG: Extracted email: '{msg_email}'")
                
                # Normaliser les emails de comparaison
                normalized_specific_email = specific_email.strip().lower() if specific_email else ''
                
                # Appliquer les filtres
                should_include = False
                
                if user_filter == "Email spécifique":
                    # Filtrage par email spécifique (pour utilisateurs non-admin)
                    if normalized_specific_email and msg_email == normalized_specific_email:
                        should_include = True
                elif user_filter == "Tous les utilisateurs":
                    should_include = True
                    # Si un email spécifique est fourni, l'appliquer en plus
                    if normalized_specific_email and msg_email != normalized_specific_email:
                        should_include = False
                elif user_filter == "Admin (ID: 0)" and msg_user_id == 0:
                    should_include = True
                    # Si un email spécifique est fourni, l'appliquer en plus
                    if normalized_specific_email and msg_email != normalized_specific_email:
                        should_include = False
                elif user_filter == "Utilisateur (ID: 1)" and msg_user_id == 1:
                    should_include = True
                    # Si un email spécifique est fourni, l'appliquer en plus
                    if normalized_specific_email and msg_email != normalized_specific_email:
                        should_include = False
                
                # Appliquer le filtre de pattern d'email
                if should_include and email_pattern:
                    if st.session_state.get('debug_email_filter', False):
                        st.write(f"DEBUG: Applying pattern '{email_pattern}' to email '{msg_email}'")
                    pattern_result = match_email_pattern(msg_email, email_pattern)
                    if st.session_state.get('debug_email_filter', False):
                        st.write(f"DEBUG: Pattern match result: {pattern_result}")
                    should_include = pattern_result
                
                if should_include:
                    filtered_messages.append(msg)
            else:
                # Garder les messages sans question (réponses, etc.)
                filtered_messages.append(msg)
        
        # Ajouter la conversation si elle a des messages après filtrage
        if filtered_messages:
            conv_copy = conv.copy()
            conv_copy['messages'] = filtered_messages
            final_conversations.append(conv_copy)
    
    questions_stats = {
        "admin_questions": admin_questions,
        "user_questions": user_questions,
        "total_questions": total_questions
    }
    
    return final_conversations, questions_stats

def analyze_questions_by_user_type():
    """
    Analyse les questions par type d'utilisateur (Admin ID:0 vs Utilisateur ID:1)
    Les questions non-identifiées sont attribuées à l'ID 1 par défaut
    """
    conversations = load_conversations_from_firebase()
    
    if not conversations:
        return {
            "admin_questions": 0,
            "user_questions": 0,
            "total_questions": 0
        }
    
    admin_questions = 0
    user_questions = 0
    
    for conv in conversations:
        messages = conv.get('messages', [])
        
        for msg in messages:
            if msg.get('question', '').strip():  # Si c'est une question non vide
                # Récupérer l'user_id depuis les métadonnées du message
                msg_user_id = msg.get('metadata', {}).get('user_id', 1)  # Défaut à 1 si non défini
                
                if msg_user_id == 0:
                    admin_questions += 1
                else:
                    user_questions += 1
    
    return {
        "admin_questions": admin_questions,
        "user_questions": user_questions,
        "total_questions": admin_questions + user_questions
    }

def count_questions_with_without_docs(conversations=None):
    """
    Compte le nombre de questions avec et sans documents
    Retourne un dictionnaire avec les statistiques
    """
    if conversations is None:
        conversations = load_conversations_from_firebase()
    
    if not conversations:
        return {
            "avec_documents_total": 0,
            "sans_documents_total": 0,
            "total_questions": 0
        }
    
    # Compteurs pour le total
    total_avec_docs = 0
    total_sans_docs = 0
    total_questions = 0
    
    for conv in conversations:
        for msg in conv['messages']:
            # Récupérer le contenu de la question
            question_content = msg.get('question', '').strip()
            
            # Ignorer les messages vides
            if not question_content:
                continue
            
            # Compter toutes les questions
            total_questions += 1
            
            # Vérifier si la question a des documents
            docs = msg.get('docs')
            has_docs = docs and isinstance(docs, list) and len(docs) > 0
            
            # Compter le total
            if has_docs:
                total_avec_docs += 1
            else:
                total_sans_docs += 1
    
    return {
        "avec_documents_total": total_avec_docs,
        "sans_documents_total": total_sans_docs,
        "total_questions": total_questions
    }

def get_detailed_questions_stats(conversations=None):
    """
    Retourne des statistiques détaillées sur les questions avec exemples
    """
    if conversations is None:
        conversations = load_conversations_from_firebase()
    
    if not conversations:
        return {"error": "Aucune conversation trouvée"}
    
    questions_avec_docs = []
    questions_sans_docs = []
    
    for conv in conversations:
        for msg in conv['messages']:
            question_content = msg.get('question', '').strip()
            
            if not question_content:
                continue
            
            # Vérifier si la question a des documents
            docs = msg.get('docs')
            has_docs = docs and isinstance(docs, list) and len(docs) > 0
            
            question_info = {
                "question": question_content,
                "timestamp": msg.get('timestamp', 0),
                "docs_count": len(docs) if docs else 0
            }
            
            if has_docs:
                questions_avec_docs.append(question_info)
            else:
                questions_sans_docs.append(question_info)
    
    return {
        "avec_documents": questions_avec_docs,
        "sans_documents": questions_sans_docs
    }

def analyze_conversations(conversations=None):
    """
    Analyse les conversations pour identifier les types et caractéristiques
    """
    if conversations is None:
        conversations = load_conversations_from_firebase()
    
    if not conversations:
        return {
            "error": "Aucune conversation trouvée",
            "stats": {
                "total_conversations": 0,
                "single_question": 0,
                "multi_questions": 0,
                "avg_messages_per_conv": 0,
                "max_messages": 0,
                "min_messages": 0
            }
        }
    
    conversation_stats = {
        "single_question": [],  # Conversations avec 1 question
        "multi_questions": [],  # Conversations avec 2+ questions
        "long_conversations": [],  # Conversations avec 3+ questions
        "empty_conversations": [],  # Conversations sans messages valides
    }
    
    stats = {
        "total_conversations": len(conversations),
        "single_question": 0,
        "multi_questions": 0,
        "long_conversations": 0,
        "empty_conversations": 0,
        "total_messages": 0,
        "avg_messages_per_conv": 0,
        "max_messages": 0,
        "min_messages": float('inf')
    }
    
    for conv in conversations:
        messages = conv.get('messages', [])
        valid_messages = [msg for msg in messages if msg.get('question', '').strip()]
        message_count = len(valid_messages)
        
        stats["total_messages"] += message_count
        
        if message_count == 0:
            stats["empty_conversations"] += 1
            conversation_stats["empty_conversations"].append({
                "id": conv['id'],
                "metadata": conv.get('metadata', {}),
                "message_count": 0
            })
        elif message_count == 1:
            stats["single_question"] += 1
            conversation_stats["single_question"].append({
                "id": conv['id'],
                "metadata": conv.get('metadata', {}),
                "message_count": 1,
                "question": valid_messages[0].get('question', ''),
                "timestamp": valid_messages[0].get('timestamp', 0),
                "modele": valid_messages[0].get('modele', 'unknown'),
                "has_docs": bool(valid_messages[0].get('docs'))
            })
        else:
            stats["multi_questions"] += 1
            
            # Créer les données communes pour les conversations multi-questions
            conv_data = {
                "id": conv['id'],
                "metadata": conv.get('metadata', {}),
                "message_count": message_count,
                "questions": [
                    {
                        "question": msg.get('question', ''),
                        "timestamp": msg.get('timestamp', 0),
                        "modele": msg.get('modele', 'unknown'),
                        "has_docs": bool(msg.get('docs'))
                    }
                    for msg in valid_messages
                ],
                "first_question": valid_messages[0].get('question', ''),
                "last_question": valid_messages[-1].get('question', '')
            }
            
            conversation_stats["multi_questions"].append(conv_data)
            
            # Si c'est une conversation longue (3+ questions), l'ajouter aussi à cette catégorie
            if message_count >= 3:
                stats["long_conversations"] += 1
                conversation_stats["long_conversations"].append(conv_data)
        
        # Mettre à jour min/max
        if message_count > 0:
            stats["max_messages"] = max(stats["max_messages"], message_count)
            stats["min_messages"] = min(stats["min_messages"], message_count)
    
    # Calculer la moyenne
    if stats["total_conversations"] > 0:
        stats["avg_messages_per_conv"] = stats["total_messages"] / stats["total_conversations"]
    
    # Si pas de messages valides, ajuster min_messages
    if stats["min_messages"] == float('inf'):
        stats["min_messages"] = 0
    
    return {
        "stats": stats,
        "conversations": conversation_stats
    }

def get_conversation_duration_stats(conversations=None):
    """
    Calcule les statistiques de durée des conversations multi-questions
    """
    if conversations is None:
        conversations = load_conversations_from_firebase()
    
    if not conversations:
        return {"error": "Aucune conversation trouvée"}
    
    duration_stats = []
    
    for conv in conversations:
        messages = conv.get('messages', [])
        valid_messages = [msg for msg in messages if msg.get('question', '').strip()]
        
        if len(valid_messages) > 1:
            # Calculer la durée entre premier et dernier message
            timestamps = [msg.get('timestamp', 0) for msg in valid_messages]
            timestamps = [ts for ts in timestamps if ts > 0]  # Filtrer les timestamps invalides
            
            if len(timestamps) > 1:
                timestamps.sort()
                duration_seconds = timestamps[-1] - timestamps[0]
                duration_minutes = duration_seconds / 60
                
                duration_stats.append({
                    "id": conv['id'],
                    "message_count": len(valid_messages),
                    "duration_seconds": duration_seconds,
                    "duration_minutes": duration_minutes,
                    "duration_hours": duration_minutes / 60,
                    "first_timestamp": timestamps[0],
                    "last_timestamp": timestamps[-1]
                })
    
    # Calculer les statistiques globales
    if duration_stats:
        durations_minutes = [stat["duration_minutes"] for stat in duration_stats]
        avg_duration = sum(durations_minutes) / len(durations_minutes)
        max_duration = max(durations_minutes)
        min_duration = min(durations_minutes)
        
        return {
            "conversations": duration_stats,
            "summary": {
                "count": len(duration_stats),
                "avg_duration_minutes": avg_duration,
                "max_duration_minutes": max_duration,
                "min_duration_minutes": min_duration,
                "avg_duration_readable": f"{int(avg_duration // 60)}h {int(avg_duration % 60)}m" if avg_duration > 60 else f"{int(avg_duration)}m"
            }
        }
    
    return {"conversations": [], "summary": {"count": 0}}

def analyze_long_conversations(conversations=None):
    """
    Analyse spécialisée pour les conversations de 3+ questions
    """
    if conversations is None:
        conversations = load_conversations_from_firebase()
    
    if not conversations:
        return {"error": "Aucune conversation trouvée"}
    
    long_conversations = []
    
    for conv in conversations:
        messages = conv.get('messages', [])
        valid_messages = [msg for msg in messages if msg.get('question', '').strip()]
        
        if len(valid_messages) >= 3:
            # Analyser les patterns dans cette conversation longue
            timestamps = [msg.get('timestamp', 0) for msg in valid_messages if msg.get('timestamp', 0) > 0]
            timestamps.sort()
            
            # Calculer les intervals entre questions
            intervals = []
            if len(timestamps) > 1:
                for i in range(1, len(timestamps)):
                    interval_seconds = timestamps[i] - timestamps[i-1]
                    intervals.append(interval_seconds / 60)  # en minutes
            
            # Analyser l'usage de documents
            docs_usage = [bool(msg.get('docs')) for msg in valid_messages]
            docs_count = sum(docs_usage)
            
            # Analyser les modèles utilisés
            models_used = [msg.get('modele', 'unknown') for msg in valid_messages]
            unique_models = list(set(models_used))
            
            long_conversations.append({
                "id": conv['id'],
                "message_count": len(valid_messages),
                "duration_minutes": (timestamps[-1] - timestamps[0]) / 60 if len(timestamps) > 1 else 0,
                "avg_interval_minutes": sum(intervals) / len(intervals) if intervals else 0,
                "max_interval_minutes": max(intervals) if intervals else 0,
                "min_interval_minutes": min(intervals) if intervals else 0,
                "docs_usage_count": docs_count,
                "docs_usage_percentage": (docs_count / len(valid_messages)) * 100,
                "models_used": unique_models,
                "model_switches": len(unique_models) - 1,
                "questions": [
                    {
                        "question": msg.get('question', ''),
                        "timestamp": msg.get('timestamp', 0),
                        "modele": msg.get('modele', 'unknown'),
                        "has_docs": bool(msg.get('docs')),
                        "docs_count": len(msg.get('docs', [])) if msg.get('docs') else 0
                    }
                    for msg in valid_messages
                ],
                "conversation_pattern": analyze_conversation_pattern(valid_messages)
            })
    
    # Statistiques globales pour les conversations longues
    if long_conversations:
        summary = {
            "total_count": len(long_conversations),
            "avg_length": sum(c["message_count"] for c in long_conversations) / len(long_conversations),
            "max_length": max(c["message_count"] for c in long_conversations),
            "avg_duration": sum(c["duration_minutes"] for c in long_conversations) / len(long_conversations),
            "avg_docs_usage": sum(c["docs_usage_percentage"] for c in long_conversations) / len(long_conversations),
            "most_active_models": get_most_used_models(long_conversations)
        }
    else:
        summary = {"total_count": 0}
    
    return {
        "conversations": sorted(long_conversations, key=lambda x: x["message_count"], reverse=True),
        "summary": summary
    }

def analyze_conversation_pattern(messages):
    """
    Analyse le pattern d'une conversation (docs au début, recherche après, etc.)
    """
    docs_pattern = [bool(msg.get('docs')) for msg in messages]
    
    if all(docs_pattern):
        return "Analyse pure (uniquement documents)"
    elif not any(docs_pattern):
        return "Recherche pure (aucun document)"
    elif docs_pattern[0] and not docs_pattern[-1]:
        return "Analyse → Recherche"
    elif not docs_pattern[0] and docs_pattern[-1]:
        return "Recherche → Analyse"
    else:
        return "Analyse mixte"

def get_most_used_models(conversations):
    """
    Trouve les modèles les plus utilisés dans les conversations longues
    """
    model_counts = {}
    for conv in conversations:
        for model in conv["models_used"]:
            model_counts[model] = model_counts.get(model, 0) + 1
    
    return sorted(model_counts.items(), key=lambda x: x[1], reverse=True)[:3]

def format_timestamp(timestamp):
    """Formate un timestamp en date lisible"""
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    elif hasattr(timestamp, 'timestamp'):
        return datetime.fromtimestamp(timestamp.timestamp()).strftime('%Y-%m-%d %H:%M:%S')
    else:
        return str(timestamp)

def format_date_only(timestamp):
    """Formate un timestamp en date seulement"""
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
    elif hasattr(timestamp, 'timestamp'):
        return datetime.fromtimestamp(timestamp.timestamp()).strftime('%Y-%m-%d')
    else:
        return str(timestamp)[:10]

def calculate_total_cost(conversations):
    """Calcule le coût total de toutes les conversations (exclude gemini-2.0-flash-exp from display total)"""
    total_cost = 0.0
    total_tokens = 0
    model_costs = defaultdict(float)
    model_tokens = defaultdict(int)
    
    for conv in conversations:
        for message in conv['messages']:
            metadata = message.get('metadata', {})
            modele = message.get('modele', 'unknown')
            
            # Coût direct
            cout = metadata.get('cout', {})
            if isinstance(cout, dict):
                prix = cout.get('prix', 0)
                tokens = cout.get('tokens', 0)
                
                if isinstance(prix, (int, float)):
                    # Exclude gemini-2.0-flash-exp costs from total display
                    if modele != 'gemini-2.0-flash-exp':
                        total_cost += prix
                if isinstance(tokens, (int, float)):
                    total_tokens += tokens
                
                # Par modèle (still track all costs for backend)
                model_costs[modele] += prix
                model_tokens[modele] += tokens
    
    return total_cost, total_tokens, dict(model_costs), dict(model_tokens)

def get_model_stats(conversations):
    """Statistiques par modèle"""
    model_stats = defaultdict(lambda: {
        'count': 0,
        'total_cost': 0.0,
        'total_tokens': 0,
        'avg_response_length': 0,
        'with_docs': 0,
        'with_citations': 0
    })
    
    for conv in conversations:
        for message in conv['messages']:
            modele = message.get('modele', 'unknown')
            stats = model_stats[modele]
            
            stats['count'] += 1
            
            # Coûts
            metadata = message.get('metadata', {})
            cout = metadata.get('cout', {})
            if isinstance(cout, dict):
                prix = cout.get('prix', 0)
                tokens = cout.get('tokens', 0)
                
                if isinstance(prix, (int, float)):
                    stats['total_cost'] += prix
                if isinstance(tokens, (int, float)):
                    stats['total_tokens'] += tokens
            
            # Longueur de réponse
            reponse = message.get('reponse', '')
            if reponse:
                stats['avg_response_length'] += len(reponse)
            
            # Documents
            docs = message.get('docs')
            if docs and isinstance(docs, list) and len(docs) > 0:
                stats['with_docs'] += 1
            
            # Citations
            citations = metadata.get('citations', [])
            if citations and isinstance(citations, list) and len(citations) > 0:
                stats['with_citations'] += 1
    
    # Calculer les moyennes
    for modele, stats in model_stats.items():
        if stats['count'] > 0:
            stats['avg_response_length'] = stats['avg_response_length'] // stats['count']
            stats['avg_cost'] = stats['total_cost'] / stats['count']
            stats['avg_tokens'] = stats['total_tokens'] // stats['count']
    
    return dict(model_stats)

def main():
    """
    Fonction principale du dashboard
    """
    st.set_page_config(
        page_title="Dashboard - Assistant Juridique IA", 
        layout="wide",
        page_icon="📊"
    )
    
    # Header avec style
    st.markdown("""
    <div style="background: linear-gradient(90deg, #667eea 0%, #764ba2 100%); padding: 2rem; border-radius: 10px; margin-bottom: 2rem;">
        <h1 style="color: white; text-align: center; margin: 0;">📊 Dashboard - Assistant Juridique IA</h1>
        <p style="color: white; text-align: center; margin: 0.5rem 0 0 0;">Visualisation des conversations et analytics</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar pour les contrôles
    with st.sidebar:
        st.header("⚙️ Contrôles")
        
        # Filtre par type d'utilisateur
        st.subheader("👥 Filtre Utilisateur")
        user_filter = st.selectbox(
            "Afficher les questions de:",
            ["Tous les utilisateurs", "Admin (ID: 0)", "Utilisateur (ID: 1)"],
            help="Filtrer les conversations par type d'utilisateur"
        )
        
        # Filtre par email spécifique (optionnel)
        st.subheader("📧 Filtre Email")
        
        # Choix du mode de filtrage email
        email_mode = st.radio(
            "Mode de filtrage email:",
            ["Aucun", "Email exact", "Pattern d'email"],
            help="Choisissez le type de filtre email à appliquer"
        )
        
        specific_email = ""
        email_pattern = ""
        
        if email_mode == "Email exact":
            # Vérifier si un email a été sélectionné via les boutons
            pre_filled_email = st.session_state.get('selected_email_filter', '')
            specific_email = st.text_input(
                "Email exact:",
                value=pre_filled_email,
                placeholder="ex: nom@hermine.app",
                help="Email exact à rechercher",
                key="specific_email"
            )
            # Nettoyer la sélection après utilisation
            if pre_filled_email:
                st.session_state.selected_email_filter = ""
        elif email_mode == "Pattern d'email":
            email_pattern = st.text_input(
                "Pattern d'email:",
                placeholder="ex: @numbr.fr, user@*, *@domain.com",
                help="Patterns supportés",
                key="email_pattern"
            )
            
            if email_pattern:
                st.info(f"🔍 Pattern actif: `{email_pattern}`")
                with st.expander("📋 Aide sur les patterns"):
                    st.write("**Exemples de patterns:**")
                    st.write("• `@numbr.fr` → emails se terminant par @numbr.fr")
                    st.write("• `test@*` → emails commençant par test@")
                    st.write("• `*@gmail.com` → tous les emails Gmail")
                    st.write("• `*hermine*` → emails contenant 'hermine'")
        
        
        # Filtre par période
        st.subheader("📅 Filtre temporel")
        
        # Choix du mode de filtrage date
        date_mode = st.radio(
            "Mode de filtrage temporel:",
            ["Période relative", "Date précise"],
            help="Choisissez le type de filtre temporel à appliquer"
        )
        
        date_filter = "Toutes"
        precise_date = None
        
        if date_mode == "Période relative":
            date_filter = st.selectbox(
                "Période relative:",
                ["Toutes", "7 derniers jours", "30 derniers jours", "90 derniers jours"],
                help="Filtrer les conversations par période relative",
                key="date_filter"
            )
        elif date_mode == "Date précise":
            precise_date = st.date_input(
                "Date précise:",
                value=None,
                help="Sélectionner une date spécifique pour voir les conversations de cette journée",
                key="precise_date"
            )
            if precise_date:
                st.info(f"📅 Conversations du {precise_date.strftime('%d/%m/%Y')}")
            else:
                precise_date = None
        
        
        # Affichage des statistiques de base
        st.subheader("📈 Info Rapide")
    
    # --- Chargement des données ---
    with st.spinner("🔄 Chargement des conversations depuis Firebase..."):
        conversations = load_conversations_from_firebase()
    
    if not conversations:
        st.warning("⚠️ Aucune conversation trouvée ou erreur de connexion Firebase.")
        st.info("💡 Utilisez d'abord l'assistant juridique pour générer des conversations.")
        return
    
    # Filtrage des données
    filtered_conversations, questions_stats = filter_conversations(
        conversations, date_filter, user_filter, specific_email, precise_date, email_pattern
    )
    
    # Info dans la sidebar
    with st.sidebar:
        st.metric("📊 Conversations", len(filtered_conversations))
        st.metric("❓ Questions", questions_stats["total_questions"])
        st.metric("🔐 Admin", questions_stats["admin_questions"])
        st.metric("👤 Utilisateur", questions_stats["user_questions"])
        
        # Debug info for email filtering
        if st.session_state.get('debug_email_filter', False):
            st.subheader("🐛 Debug Email Info")
            # Sample the first few conversations to show email structure
            if conversations:
                emails_found = set()
                for conv in conversations[:5]:  # Sample first 5 conversations
                    for msg in conv.get('messages', []):
                        if msg.get('question', '').strip():
                            metadata = msg.get('metadata', {})
                            user_info = metadata.get('user_info', {})
                            email_paths = [
                                user_info.get('user_email', ''),
                                metadata.get('email', ''),
                                user_info.get('email', '') if isinstance(user_info, dict) else ''
                            ]
                            for email in email_paths:
                                if email and email.strip():
                                    emails_found.add(email.strip().lower())
                
                if emails_found:
                    st.write("Emails trouvés dans les données:")
                    for email in sorted(emails_found):
                        st.write(f"• {email}")
                else:
                    st.warning("Aucun email trouvé dans les métadonnées")
                    # Show a sample metadata structure
                    if conversations and conversations[0].get('messages'):
                        sample_metadata = conversations[0]['messages'][0].get('metadata', {})
                        st.json(sample_metadata)
        
        # Info sur les filtres actifs
        filters_active = []
        if specific_email:
            filters_active.append(f"📧 Email: {specific_email}")
        if email_pattern:
            filters_active.append(f"🔍 Pattern: {email_pattern}")
        if precise_date:
            filters_active.append(f"📅 Date: {precise_date.strftime('%d/%m/%Y')}")
        
        if filters_active:
            st.success("🎯 Filtres actifs:")
            for filter_info in filters_active:
                st.write(f"• {filter_info}")
    
    # Status avec style
    if len(filtered_conversations) < len(conversations):
        filter_info = []
        if user_filter != "Tous les utilisateurs":
            filter_info.append(f"Type: {user_filter}")
        if specific_email:
            filter_info.append(f"Email: {specific_email}")
        if email_pattern:
            filter_info.append(f"Pattern: {email_pattern}")
        if date_filter != "Toutes":
            filter_info.append(f"Période: {date_filter}")
        if precise_date:
            filter_info.append(f"Date: {precise_date.strftime('%d/%m/%Y')}")
        
        filter_text = " | ".join(filter_info) if filter_info else "filtrées"
        st.info(f"📊 {len(filtered_conversations)} conversations sur {len(conversations)} ({filter_text})")
    else:
        st.success(f"✅ {len(conversations)} conversations chargées depuis Firebase")
    
    # --- Métriques Principales ---
    st.markdown("## 📊 Vue d'Ensemble")
    
    total_cost, total_tokens, model_costs, model_tokens = calculate_total_cost(filtered_conversations)
    total_messages = sum(len(conv['messages']) for conv in filtered_conversations)
    
    # Cards avec style
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 1rem; border-radius: 10px; text-align: center; color: white;">
            <h3>💬 Conversations</h3>
            <h2>{}</h2>
        </div>
        """.format(len(filtered_conversations)), unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); padding: 1rem; border-radius: 10px; text-align: center; color: white;">
            <h3>📝 Messages</h3>
            <h2>{}</h2>
        </div>
        """.format(total_messages), unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); padding: 1rem; border-radius: 10px; text-align: center; color: white;">
            <h3>💰 Coût Total</h3>
            <h2>${:.4f}</h2>
        </div>
        """.format(total_cost), unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); padding: 1rem; border-radius: 10px; text-align: center; color: white;">
            <h3>🔤 Tokens</h3>
            <h2>{:,}</h2>
        </div>
        """.format(total_tokens), unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # --- Analyse par Type d'Utilisateur ---
    st.markdown("## 👥 Répartition par Type d'Utilisateur")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        # Métriques utilisateur
        st.markdown("### 📈 Statistiques")
        
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("🔐 Admin (ID:0)", questions_stats["admin_questions"])
        with col_b:
            st.metric("👤 Utilisateur (ID:1)", questions_stats["user_questions"])
        
        st.metric("📊 Total Questions", questions_stats["total_questions"])
    
    with col2:
        # Graphique en secteurs
        if questions_stats["admin_questions"] + questions_stats["user_questions"] > 0:
            fig_pie = px.pie(
                values=[questions_stats["admin_questions"], questions_stats["user_questions"]],
                names=["Admin (ID:0)", "Utilisateur (ID:1)"],
                title="Répartition des Questions",
                color_discrete_map={"Admin (ID:0)": "#ff6b6b", "Utilisateur (ID:1)": "#4ecdc4"}
            )
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
    
    st.divider()
    
    # --- Section Statistiques d'utilisation avancées ---
    st.markdown("## 📊 Statistiques d'utilisation avancées")
    
    # Vérifier si l'utilisateur est admin ou non selon les filtres
    is_admin_view = user_filter == "Admin (ID: 0)"
    is_user_view = user_filter == "Utilisateur (ID: 1)"
    
    # Filtres de sélection pour la zone statistiques
    col_stats_filter1, col_stats_filter2 = st.columns(2)
    
    with col_stats_filter1:
        if user_filter == "Tous les utilisateurs":
            st.info("🔍 Affichage global (admin + utilisateurs)")
        elif is_admin_view:
            st.info("🔐 Vue Admin uniquement")
        else:
            st.info("👤 Vue Utilisateurs uniquement")
    
    with col_stats_filter2:
        if specific_email:
            st.info(f"📧 Email sélectionné: {specific_email}")
        elif email_pattern:
            st.info(f"🔍 Pattern email: {email_pattern}")
        else:
            st.info("📧 Tous les emails")
    
    # Calculer les statistiques pour les camemberts
    if filtered_conversations:
        # Initialiser les compteurs
        messages_per_conv_stats = {}
        doc_usage_stats = {"Avec documents": 0, "Sans documents": 0}
        docs_count_stats = {}
        
        for conv in filtered_conversations:
            # Compter les messages (questions) par conversation
            question_count = 0
            has_docs_in_conv = False
            total_docs_in_conv = 0
            
            for msg in conv['messages']:
                if msg.get('question', '').strip():
                    question_count += 1
                    
                    # Vérifier l'utilisation de documents
                    docs = msg.get('docs')
                    if docs and isinstance(docs, list) and len(docs) > 0:
                        has_docs_in_conv = True
                        total_docs_in_conv += len(docs)
            
            if question_count > 0:
                # Statistiques messages par conversation
                if question_count == 1:
                    key = "1 message"
                elif question_count <= 3:
                    key = f"{question_count} messages"
                elif question_count <= 5:
                    key = "4-5 messages"
                else:
                    key = "6+ messages"
                
                messages_per_conv_stats[key] = messages_per_conv_stats.get(key, 0) + 1
                
                # Statistiques utilisation documents
                if has_docs_in_conv:
                    doc_usage_stats["Avec documents"] += 1
                else:
                    doc_usage_stats["Sans documents"] += 1
                
                # Statistiques nombre de documents par conversation
                if total_docs_in_conv == 0:
                    doc_key = "0 document"
                elif total_docs_in_conv == 1:
                    doc_key = "1 document"
                elif total_docs_in_conv <= 3:
                    doc_key = "2-3 documents"
                elif total_docs_in_conv <= 5:
                    doc_key = "4-5 documents"
                else:
                    doc_key = "6+ documents"
                
                docs_count_stats[doc_key] = docs_count_stats.get(doc_key, 0) + 1
        
        # Afficher les camemberts
        col_pie1, col_pie2, col_pie3 = st.columns(3)
        
        with col_pie1:
            st.subheader("📊 Messages par conversation")
            if messages_per_conv_stats:
                fig_msgs = px.pie(
                    values=list(messages_per_conv_stats.values()),
                    names=list(messages_per_conv_stats.keys()),
                    title="Répartition messages/conversation",
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig_msgs.update_traces(textposition='inside', textinfo='percent+label')
                fig_msgs.update_layout(showlegend=True, legend=dict(orientation="v", yanchor="top", y=0.99, xanchor="left", x=1.01))
                st.plotly_chart(fig_msgs, use_container_width=True)
                
                # Statistiques textuelles
                total_convs = sum(messages_per_conv_stats.values())
                single_msg = messages_per_conv_stats.get("1 message", 0)
                multi_msg = total_convs - single_msg
                st.write(f"**📈 Total:** {total_convs} conversations")
                st.write(f"**🔢 1 message:** {single_msg} ({(single_msg/total_convs)*100:.1f}%)")
                st.write(f"**🔢 Multi-messages:** {multi_msg} ({(multi_msg/total_convs)*100:.1f}%)")
            else:
                st.info("Aucune donnée disponible")
        
        with col_pie2:
            st.subheader("📄 Utilisation de documents")
            if sum(doc_usage_stats.values()) > 0:
                fig_docs = px.pie(
                    values=list(doc_usage_stats.values()),
                    names=list(doc_usage_stats.keys()),
                    title="Usage de documents",
                    color_discrete_map={
                        "Avec documents": "#4CAF50",
                        "Sans documents": "#FF9800"
                    }
                )
                fig_docs.update_traces(textposition='inside', textinfo='percent+label')
                fig_docs.update_layout(showlegend=True, legend=dict(orientation="v", yanchor="top", y=0.99, xanchor="left", x=1.01))
                st.plotly_chart(fig_docs, use_container_width=True)
                
                # Statistiques textuelles
                total_usage = sum(doc_usage_stats.values())
                with_docs = doc_usage_stats["Avec documents"]
                without_docs = doc_usage_stats["Sans documents"]
                st.write(f"**📈 Total:** {total_usage} conversations")
                st.write(f"**📄 Avec docs:** {with_docs} ({(with_docs/total_usage)*100:.1f}%)")
                st.write(f"**🔍 Sans docs:** {without_docs} ({(without_docs/total_usage)*100:.1f}%)")
            else:
                st.info("Aucune donnée disponible")
        
        with col_pie3:
            st.subheader("📚 Documents par conversation")
            if docs_count_stats:
                fig_doc_count = px.pie(
                    values=list(docs_count_stats.values()),
                    names=list(docs_count_stats.keys()),
                    title="Nombre de docs/conversation",
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_doc_count.update_traces(textposition='inside', textinfo='percent+label')
                fig_doc_count.update_layout(showlegend=True, legend=dict(orientation="v", yanchor="top", y=0.99, xanchor="left", x=1.01))
                st.plotly_chart(fig_doc_count, use_container_width=True)
                
                # Statistiques textuelles
                total_doc_convs = sum(docs_count_stats.values())
                zero_docs = docs_count_stats.get("0 document", 0)
                with_docs_count = total_doc_convs - zero_docs
                st.write(f"**📈 Total:** {total_doc_convs} conversations")
                st.write(f"**📄 Avec docs:** {with_docs_count} ({(with_docs_count/total_doc_convs)*100:.1f}%)")
                st.write(f"**🔍 Sans docs:** {zero_docs} ({(zero_docs/total_doc_convs)*100:.1f}%)")
            else:
                st.info("Aucune donnée disponible")
    else:
        st.warning("Aucune conversation ne correspond aux filtres sélectionnés")
    
    st.divider()
    
    # --- Section détaillée pour un email spécifique ---
    if specific_email:
        st.markdown(f"## 📧 Détails pour l'email: {specific_email}")
        
        # Collecter toutes les conversations et messages pour cet email
        email_conversations = []
        email_messages = []
        
        for conv in filtered_conversations:
            conv_messages = []
            for msg in conv['messages']:
                if msg.get('question', '').strip():
                    msg_email = msg.get('metadata', {}).get('user_info', {}).get('user_email', '')
                    if not msg_email:
                        msg_email = msg.get('metadata', {}).get('email', '')
                    if not msg_email:
                        # Fallback: user_info without nested user_email
                        user_info = msg.get('metadata', {}).get('user_info', {})
                        if isinstance(user_info, dict):
                            msg_email = user_info.get('email', '')
                    
                    # Normalize email for comparison
                    msg_email = msg_email.strip().lower() if msg_email else ''
                    normalized_specific_email = specific_email.strip().lower() if specific_email else ''
                    
                    if msg_email == normalized_specific_email:
                        conv_messages.append(msg)
                        email_messages.append({
                            'message': msg,
                            'conv_id': conv['id'],
                            'conv_date': format_timestamp(msg.get('timestamp', 0))
                        })
            
            if conv_messages:
                email_conversations.append({
                    'conversation': conv,
                    'messages': conv_messages
                })
        
        # Métriques pour cet email
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("💬 Conversations", len(email_conversations))
        with col2:
            st.metric("❓ Messages", len(email_messages))
        with col3:
            # Calculer les documents
            docs_count = sum(1 for msg_data in email_messages 
                           if msg_data['message'].get('docs') and 
                              isinstance(msg_data['message'].get('docs'), list) and 
                              len(msg_data['message'].get('docs')) > 0)
            st.metric("📄 Avec documents", docs_count)
        with col4:
            search_count = len(email_messages) - docs_count
            st.metric("🔍 Recherches", search_count)
        
        # Affichage détaillé des conversations
        if email_conversations:
            st.markdown("### 💬 Conversations de cet utilisateur")
            
            for i, conv_data in enumerate(email_conversations):
                conv = conv_data['conversation']
                messages = conv_data['messages']
                
                with st.expander(f"📁 Conversation {i+1} - {len(messages)} message{'s' if len(messages) > 1 else ''} - ID: {conv['id'][:8]}..."):
                    for j, msg in enumerate(messages):
                        st.markdown(f"**Message {j+1}** - {format_timestamp(msg.get('timestamp', 0))}")
                        
                        # Question
                        question = msg.get('question', 'N/A')
                        st.markdown(f"**❓ Question:** {question}")
                        
                        # Modèle et documents
                        modele = msg.get('modele', 'N/A')
                        docs = msg.get('docs', [])
                        doc_info = f"📄 {len(docs)} documents" if docs and len(docs) > 0 else "🔍 Recherche web"
                        st.markdown(f"**🤖 Modèle:** {modele} | **Type:** {doc_info}")
                        
                        # Réponse
                        reponse = msg.get('reponse', 'N/A')
                        if reponse and len(reponse) > 200:
                            st.markdown(f"""
                            <details>
                            <summary><b>💡 Voir la réponse complète</b></summary>
                            <div style="margin-top: 10px; padding: 10px; background-color: #f0f2f6; border-radius: 5px; max-height: 300px; overflow-y: auto;">
                            {reponse.replace(chr(10), '<br>')}
                            </div>
                            </details>
                            """, unsafe_allow_html=True)
                        else:
                            st.markdown(f"**💡 Réponse:** {reponse[:200]}..." if len(reponse) > 200 else f"**💡 Réponse:** {reponse}")
                        
                        if j < len(messages) - 1:
                            st.markdown("---")
        else:
            st.info("Aucune conversation trouvée pour cet email dans les données filtrées.")
        
        st.divider()
    
    # --- Section Statistiques Email ---
    st.markdown("## 📧 Statistiques des Connexions Email")
    
    with st.spinner("🔄 Chargement des statistiques d'emails..."):
        email_stats = get_email_connection_stats()
    
    if email_stats:
        # Métriques globales
        total_unique_emails = len(email_stats)
        total_all_connections = sum(stat['total_connections'] for stat in email_stats)
        avg_connections_per_user = total_all_connections / total_unique_emails if total_unique_emails > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("📧 Emails uniques connectés", total_unique_emails)
        
        with col2:
            st.metric("🔄 Total connexions", total_all_connections)
        
        with col3:
            st.metric("📊 Moyenne connexions/utilisateur", f"{avg_connections_per_user:.1f}")
        
        # Tableau détaillé des statistiques email
        st.markdown("### 📊 Détail des Connexions par Email")
        
        # Créer un DataFrame pour l'affichage
        email_df = pd.DataFrame([
            {
                'Email': stat['email'],
                'Nombre de connexions': stat['total_connections'],
                'Dernière connexion': stat['last_connection']
            }
            for stat in email_stats
        ])
        
        # Afficher le tableau avec possibilité de cliquer sur l'email pour filtrer
        st.dataframe(
            email_df,
            use_container_width=True,
            hide_index=True
        )
        
        # Boutons de filtre rapide pour les emails les plus actifs
        if len(email_stats) > 0:
            st.markdown("### 🎯 Filtrage Rapide")
            st.markdown("Cliquez sur un email pour le filtrer dans les conversations :")
            
            # Afficher les 5 emails les plus actifs comme boutons
            top_emails = email_stats[:5]
            
            cols = st.columns(min(len(top_emails), 5))
            for i, stat in enumerate(top_emails):
                with cols[i]:
                    if st.button(
                        f"📧 {stat['email'][:20]}{'...' if len(stat['email']) > 20 else ''}\n({stat['total_connections']} connexions)",
                        key=f"email_filter_{i}_{stat['email']}"
                    ):
                        # Stocker l'email sélectionné pour le filtrage
                        st.session_state.selected_email_filter = stat['email']
                        st.rerun()
        
        # Graphique des connexions par email (top 10)
        if len(email_stats) >= 2:
            st.markdown("### 📈 Top 10 des Emails par Nombre de Connexions")
            
            top_10_emails = email_stats[:10]
            
            fig_email_connections = px.bar(
                x=[stat['email'][:30] + '...' if len(stat['email']) > 30 else stat['email'] for stat in top_10_emails],
                y=[stat['total_connections'] for stat in top_10_emails],
                title="Nombre de Connexions par Email",
                labels={'x': 'Email', 'y': 'Nombre de connexions'},
                color=[stat['total_connections'] for stat in top_10_emails],
                color_continuous_scale='viridis'
            )
            fig_email_connections.update_layout(
                xaxis_tickangle=-45,
                height=500
            )
            st.plotly_chart(fig_email_connections, use_container_width=True)
    else:
        st.info("ℹ️ Aucune donnée de connexion email trouvée.")
    
    st.divider()
    
    # --- Section Association Conversations-Email ---
    st.markdown("## 💬 Conversations par Email Utilisateur")
    
    with st.spinner("🔄 Chargement des associations conversations-email..."):
        conversations_with_email = get_conversations_by_user_email()
    
    if conversations_with_email:
        # Statistiques globales
        total_conversations = len(conversations_with_email)
        emails_with_conversations = len(set(conv['email'] for conv in conversations_with_email if conv['email']))
        conversations_without_email = len([conv for conv in conversations_with_email if not conv['email']])
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("📊 Total conversations", total_conversations)
        
        with col2:
            st.metric("📧 Emails avec conversations", emails_with_conversations)
        
        with col3:
            st.metric("⚠️ Conversations sans email", conversations_without_email)
        
        # Grouper les conversations par email
        conversations_by_email = {}
        for conv in conversations_with_email:
            email = conv['email'] or 'Email non défini'
            if email not in conversations_by_email:
                conversations_by_email[email] = []
            conversations_by_email[email].append(conv)
        
        # Tableau résumé par email
        st.markdown("### 📊 Résumé des Conversations par Email")
        
        email_summary = []
        for email, conversations in conversations_by_email.items():
            total_messages = sum(conv['message_count'] for conv in conversations)
            latest_conversation = max(conversations, key=lambda x: x.get('created_at') or datetime.min)
            latest_date = latest_conversation.get('created_at')
            
            if hasattr(latest_date, 'strftime'):
                latest_date_str = latest_date.strftime('%Y-%m-%d %H:%M')
            elif latest_date:
                latest_date_str = str(latest_date)[:19]
            else:
                latest_date_str = "Date inconnue"
            
            email_summary.append({
                'Email': email,
                'Nb Conversations': len(conversations),
                'Total Messages': total_messages,
                'Dernière Conversation': latest_date_str
            })
        
        # Trier par nombre de conversations décroissant
        email_summary = sorted(email_summary, key=lambda x: x['Nb Conversations'], reverse=True)
        
        email_summary_df = pd.DataFrame(email_summary)
        st.dataframe(email_summary_df, use_container_width=True, hide_index=True)
        
        # Section détaillée avec sélecteur d'email
        st.markdown("### 🔍 Explorer les Conversations par Email")
        
        # Selectbox pour choisir un email
        selected_email = st.selectbox(
            "Sélectionnez un email pour voir ses conversations :",
            options=['Tous'] + list(conversations_by_email.keys()),
            index=0
        )
        
        if selected_email != 'Tous':
            st.markdown(f"#### 📧 Conversations de : {selected_email}")
            
            user_conversations = conversations_by_email[selected_email]
            
            # Métriques pour cet email
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("💬 Conversations", len(user_conversations))
            
            with col2:
                total_msg = sum(conv['message_count'] for conv in user_conversations)
                st.metric("📝 Messages total", total_msg)
            
            with col3:
                avg_msg = total_msg / len(user_conversations) if user_conversations else 0
                st.metric("📊 Messages/conversation", f"{avg_msg:.1f}")
            
            # Liste des conversations
            for i, conv in enumerate(user_conversations[:10]):  # Limiter à 10 pour la performance
                with st.expander(f"📁 Conversation {i+1} - {conv['message_count']} messages - ID: {conv['id'][:8]}..."):
                    
                    # Informations sur la conversation
                    col_info1, col_info2 = st.columns(2)
                    
                    with col_info1:
                        created_at = conv.get('created_at')
                        if hasattr(created_at, 'strftime'):
                            created_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
                        elif created_at:
                            created_str = str(created_at)[:19]
                        else:
                            created_str = "Date inconnue"
                        st.write(f"**📅 Créée :** {created_str}")
                    
                    with col_info2:
                        st.write(f"**📊 Messages :** {conv['message_count']}")
                    
                    # Aperçu des messages (3 premiers)
                    messages = conv['messages'][:3]
                    for j, msg in enumerate(messages):
                        if msg.get('question'):
                            question = msg['question'][:100] + "..." if len(msg['question']) > 100 else msg['question']
                            st.write(f"**Q{j+1}:** {question}")
                    
                    if len(conv['messages']) > 3:
                        st.write(f"... et {len(conv['messages']) - 3} autres messages")
            
            if len(user_conversations) > 10:
                st.info(f"📋 Affichage des 10 premières conversations sur {len(user_conversations)} total")
        
        # Graphique de répartition des conversations par email (top 10)
        if len(conversations_by_email) >= 2:
            st.markdown("### 📈 Top 10 des Emails par Nombre de Conversations")
            
            # Préparer les données pour le graphique
            email_counts = [(email, len(convs)) for email, convs in conversations_by_email.items()]
            email_counts = sorted(email_counts, key=lambda x: x[1], reverse=True)[:10]
            
            fig_conv_by_email = px.bar(
                x=[email[:30] + '...' if len(email) > 30 else email for email, count in email_counts],
                y=[count for email, count in email_counts],
                title="Nombre de Conversations par Email",
                labels={'x': 'Email', 'y': 'Nombre de conversations'},
                color=[count for email, count in email_counts],
                color_continuous_scale='viridis'
            )
            fig_conv_by_email.update_layout(
                xaxis_tickangle=-45,
                height=500
            )
            st.plotly_chart(fig_conv_by_email, use_container_width=True)
    
    else:
        st.info("ℹ️ Aucune conversation avec association email trouvée.")
    
    st.divider()
    
    # --- Analyse des Questions ---
    st.markdown("## 📋 Analyse Détaillée")
    
    # Tabs pour organiser les analyses
    tab1, tab2, tab3 = st.tabs(["📄 Documents vs Recherche", "💬 Conversations", "📈 Modèles & Coûts"])
    
    with tab1:
        st.markdown("### 📄 Documents vs Recherche")
        
        with st.spinner("🔄 Calcul des statistiques documents..."):
            doc_stats = count_questions_with_without_docs(filtered_conversations)
        
        # Section statistiques
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("📄 Questions avec documents", doc_stats["avec_documents_total"])
        
        with col2:
            st.metric("🔍 Questions sans documents", doc_stats["sans_documents_total"])
        
        with col3:
            st.metric("📊 Total questions", doc_stats["total_questions"])
        
        # Graphique en secteurs
        if doc_stats["total_questions"] > 0:
            fig = px.pie(
                values=[doc_stats["avec_documents_total"], doc_stats["sans_documents_total"]],
                names=["Avec documents", "Sans documents"],
                title="Répartition Documents vs Recherche",
                color_discrete_map={
                    "Avec documents": "#4CAF50",
                    "Sans documents": "#2196F3"
                }
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Section détaillée optionnelle
        with st.expander("🔍 Voir les détails et exemples"):
            detailed_stats = get_detailed_questions_stats(filtered_conversations)
            
            if "error" not in detailed_stats:
                tab1_details, tab2_details = st.tabs(["📄 Avec documents", "🔍 Sans documents"])
                
                with tab1_details:
                    st.write(f"**{len(detailed_stats['avec_documents'])} questions avec documents :**")
                    if detailed_stats['avec_documents']:
                        for i, q in enumerate(detailed_stats['avec_documents'][:10]):  # Limite à 10 exemples
                            st.write(f"**{i+1}.** {q['question']} *(docs: {q['docs_count']})*")
                        if len(detailed_stats['avec_documents']) > 10:
                            st.write(f"... et {len(detailed_stats['avec_documents']) - 10} autres")
                
                with tab2_details:
                    st.write(f"**{len(detailed_stats['sans_documents'])} questions sans documents :**")
                    if detailed_stats['sans_documents']:
                        for i, q in enumerate(detailed_stats['sans_documents'][:10]):  # Limite à 10 exemples
                            st.write(f"**{i+1}.** {q['question']}")
                        if len(detailed_stats['sans_documents']) > 10:
                            st.write(f"... et {len(detailed_stats['sans_documents']) - 10} autres")
    
    with tab2:
        st.markdown("### 💬 Analyse des Conversations")
        
        with st.spinner("🔄 Analyse des conversations en cours..."):
            conv_analysis = analyze_conversations(filtered_conversations)
        
        if "error" not in conv_analysis:
            stats = conv_analysis["stats"]
            conv_data = conv_analysis["conversations"]
            
            # Métriques principales
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                st.metric("💬 Total Conversations", stats["total_conversations"])
            
            with col2:
                st.metric("1️⃣ Conversations simples", stats["single_question"])
            
            with col3:
                st.metric("🔄 Multi-questions (2+)", stats["multi_questions"])
            
            with col4:
                st.metric("📈 Conversations longues (3+)", stats["long_conversations"])
            
            with col5:
                st.metric("📊 Messages par conversation", f"{stats['avg_messages_per_conv']:.1f}")
            
            # Graphique de répartition
            if stats["total_conversations"] > 0:
                fig_conv = px.pie(
                    values=[stats["single_question"], stats["multi_questions"] - stats["long_conversations"], stats["long_conversations"]],
                    names=["Simples (1 question)", "Multi-questions (2)", "Longues (3+)"],
                    title="Répartition des types de conversations",
                    color_discrete_map={
                        "Simples (1 question)": "#FF9800",
                        "Multi-questions (2)": "#2196F3", 
                        "Longues (3+)": "#9C27B0"
                    }
                )
                st.plotly_chart(fig_conv, use_container_width=True)
            
            # Statistiques de durée pour conversations multi-questions
            if stats["multi_questions"] > 0:
                with st.spinner("⏱️ Calcul des durées de conversation..."):
                    duration_stats = get_conversation_duration_stats(filtered_conversations)
                
                if "error" not in duration_stats and duration_stats["summary"]["count"] > 0:
                    st.subheader("⏱️ Durées des Conversations Multi-Questions")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("🕐 Durée moyenne", duration_stats["summary"]["avg_duration_readable"])
                    with col2:
                        st.metric("⏱️ Durée max", f"{int(duration_stats['summary']['max_duration_minutes'])}m")
                    with col3:
                        st.metric("⚡ Durée min", f"{int(duration_stats['summary']['min_duration_minutes'])}m")
            
            # Section détaillée pour les conversations
            with st.expander("🔍 Explorer les conversations par type"):
                tab_conv_simple, tab_conv_multi, tab_conv_stats = st.tabs(["1️⃣ Simples", "🔄 Multi-questions", "📊 Statistiques détaillées"])
                
                with tab_conv_simple:
                    st.write(f"**{len(conv_data['single_question'])} conversations simples (1 question) :**")
                    
                    # Option pour afficher toutes les conversations simples ou seulement un aperçu
                    show_all_simple = st.checkbox("📋 Afficher toutes les conversations simples", value=False)
                    
                    if conv_data["single_question"]:
                        # Déterminer combien de conversations afficher
                        display_limit_simple = len(conv_data["single_question"]) if show_all_simple else min(10, len(conv_data["single_question"]))
                        conversations_to_show_simple = conv_data["single_question"][:display_limit_simple]
                        
                        for i, conv in enumerate(conversations_to_show_simple):
                            docs_icon = "📄" if conv["has_docs"] else "🔍"
                            timestamp_str = format_timestamp(conv["timestamp"])
                            # Afficher la question complète ou tronquée selon la longueur
                            question = conv['question']
                            if len(question) > 150:
                                st.write(f"**{i+1}.** {docs_icon} {question[:150]}... *(Modèle: {conv['modele']}, {timestamp_str})* - ID: `{conv['id'][:8]}...`")
                                st.markdown(f"<details><summary>📖 Voir la question complète</summary><p>{question}</p></details>", unsafe_allow_html=True)
                            else:
                                st.write(f"**{i+1}.** {docs_icon} {question} *(Modèle: {conv['modele']}, {timestamp_str})* - ID: `{conv['id'][:8]}...`")
                            
                            # Option pour voir la réponse
                            show_response_key = f"show_response_simple_{conv['id'][:8]}_{i}"
                            if st.checkbox(f"💡 Voir la réponse", key=show_response_key):
                                # Retrouver la réponse dans les conversations originales
                                response_text = "Réponse non trouvée"
                                for orig_conv in conversations:
                                    if orig_conv['id'] == conv['id']:
                                        # Pour les conversations simples, prendre le premier message avec une réponse
                                        for msg in orig_conv['messages']:
                                            question_msg = msg.get('question', '').strip()
                                            if question_msg and msg.get('reponse'):
                                                response_text = msg.get('reponse', 'Réponse non disponible')
                                                break
                                        break
                                
                                if len(response_text) > 500:
                                    st.text_area(
                                        "Réponse complète:", 
                                        response_text, 
                                        height=200, 
                                        disabled=True,
                                        key=f"response_text_simple_{conv['id'][:8]}_{i}"
                                    )
                                else:
                                    st.write(f"**💡 Réponse :** {response_text}")
                            
                            st.write("---")
                        
                        if not show_all_simple and len(conv_data["single_question"]) > 10:
                            st.info(f"📋 Cochez 'Afficher toutes les conversations simples' pour voir les {len(conv_data['single_question']) - 10} autres conversations")
                
                with tab_conv_multi:
                    st.write(f"**{len(conv_data['multi_questions'])} conversations multi-questions (2+ questions) :**")
                    
                    # Option pour afficher toutes les conversations multi-questions ou seulement un aperçu
                    show_all_multi = st.checkbox("📋 Afficher toutes les conversations multi-questions", value=False)
                    
                    if conv_data["multi_questions"]:
                        # Déterminer combien de conversations afficher
                        display_limit_multi = len(conv_data["multi_questions"]) if show_all_multi else min(5, len(conv_data["multi_questions"]))
                        conversations_to_show_multi = conv_data["multi_questions"][:display_limit_multi]
                        
                        for i, conv in enumerate(conversations_to_show_multi):
                            st.write(f"**Conversation {i+1}** ({conv['message_count']} questions) - ID: `{conv['id'][:12]}...`")
                            st.write(f"   📝 Première: {conv['first_question']}")
                            st.write(f"   📝 Dernière: {conv['last_question']}")
                            
                            # Option pour voir toutes les questions ou juste un aperçu
                            show_all_questions_multi_key = f"show_all_q_multi_{conv['id'][:8]}_{i}"
                            show_all_questions_multi = st.checkbox(f"📝 Voir toutes les {len(conv['questions'])} questions", key=show_all_questions_multi_key)
                            
                            if show_all_questions_multi:
                                st.write("**Toutes les questions :**")
                                for j, q in enumerate(conv['questions'], 1):
                                    docs_icon = "📄" if q["has_docs"] else "🔍"
                                    timestamp_str = format_timestamp(q["timestamp"])
                                    st.write(f"   {j}. {docs_icon} {q['question']} *(Modèle: {q['modele']}, {timestamp_str})*")
                            else:
                                # Affichage par défaut de toutes les questions (car généralement 2-5 questions max)
                                st.write(f"   **Détail des {conv['message_count']} questions :**")
                                for j, q in enumerate(conv['questions'], 1):
                                    docs_icon = "📄" if q["has_docs"] else "🔍"
                                    timestamp_str = format_timestamp(q["timestamp"])
                                    st.write(f"   {j}. {docs_icon} {q['question']} *(Modèle: {q['modele']}, {timestamp_str})*")
                            
                            st.write("---")
                        
                        if not show_all_multi and len(conv_data["multi_questions"]) > 5:
                            st.info(f"📋 Cochez 'Afficher toutes les conversations multi-questions' pour voir les {len(conv_data['multi_questions']) - 5} autres conversations")
                
                with tab_conv_stats:
                    st.write("**📊 Statistiques détaillées :**")
                    st.write(f"• **Messages total :** {stats['total_messages']}")
                    st.write(f"• **Messages par conversation (moyenne) :** {stats['avg_messages_per_conv']:.2f}")
                    st.write(f"• **Maximum de messages dans une conversation :** {stats['max_messages']}")
                    st.write(f"• **Minimum de messages dans une conversation :** {stats['min_messages']}")
                    
                    if stats["empty_conversations"] > 0:
                        st.write(f"• **⚠️ Conversations vides :** {stats['empty_conversations']}")
            
            # Section spécialisée pour les conversations longues (3+ questions)
            if stats["long_conversations"] > 0:
                st.subheader("📈 Conversations Longues (3+ questions)")
                
                with st.spinner("🔄 Analyse des conversations longues..."):
                    long_conv_analysis = analyze_long_conversations(filtered_conversations)
                
                if "error" not in long_conv_analysis and long_conv_analysis["summary"]["total_count"] > 0:
                    summary = long_conv_analysis["summary"]
                    
                    # Métriques des conversations longues
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("📈 Conversations longues", summary["total_count"])
                    
                    with col2:
                        st.metric("📊 Longueur moyenne", f"{summary['avg_length']:.1f} questions")
                    
                    with col3:
                        st.metric("⏱️ Durée moyenne", f"{summary['avg_duration']:.0f}m")
                    
                    with col4:
                        st.metric("📄 Usage docs moyen", f"{summary['avg_docs_usage']:.1f}%")
                    
                    # Interface détaillée pour les conversations longues
                    with st.expander("🔍 Explorer les conversations longues en détail"):
                        tab_patterns, tab_models, tab_details = st.tabs(["🎯 Patterns", "🤖 Modèles", "📋 Détails des conversations"])
                        
                        with tab_patterns:
                            st.write("**🎯 Patterns d'utilisation dans les conversations longues :**")
                            
                            pattern_counts = {}
                            for conv in long_conv_analysis["conversations"]:
                                pattern = conv["conversation_pattern"]
                                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
                            
                            if pattern_counts:
                                st.write("**Répartition des patterns :**")
                                for pattern, count in pattern_counts.items():
                                    percentage = (count / len(long_conv_analysis["conversations"])) * 100
                                    st.write(f"• **{pattern}** : {count} conversations ({percentage:.1f}%)")
                            
                            st.write(f"**Usage des documents :** {summary['avg_docs_usage']:.1f}% en moyenne")
                            
                            # Modèles les plus utilisés
                            if "most_active_models" in summary:
                                st.write("**🤖 Modèles les plus utilisés :**")
                                for model, count in summary["most_active_models"]:
                                    st.write(f"• **{model}** : {count} utilisations")
                        
                        with tab_models:
                            st.write("**🤖 Analyse des modèles dans les conversations longues :**")
                            
                            # Statistiques sur les changements de modèles
                            model_switches = [conv["model_switches"] for conv in long_conv_analysis["conversations"]]
                            avg_switches = sum(model_switches) / len(model_switches) if model_switches else 0
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("🔄 Changements modèles (moyenne)", f"{avg_switches:.1f}")
                            with col2:
                                max_switches = max(model_switches) if model_switches else 0
                                st.metric("🔄 Max changements modèles", max_switches)
                            
                            # Modèles les plus utilisés avec détails
                            if "most_active_models" in summary:
                                st.write("**Top 3 des modèles :**")
                                for i, (model, count) in enumerate(summary["most_active_models"], 1):
                                    st.write(f"{i}. **{model}** - {count} utilisations")
                        
                        with tab_details:
                            st.write(f"**📋 Détail des {len(long_conv_analysis['conversations'])} conversations longues :**")
                            
                            # Option pour afficher toutes les conversations ou seulement un aperçu
                            show_all = st.checkbox("📋 Afficher toutes les conversations longues", value=False)
                            
                            # Trier par longueur décroissante
                            sorted_convs = sorted(long_conv_analysis["conversations"], key=lambda x: x["message_count"], reverse=True)
                            
                            # Déterminer combien de conversations afficher
                            display_limit = len(sorted_convs) if show_all else min(10, len(sorted_convs))
                            conversations_to_show = sorted_convs[:display_limit]
                            
                            for i, conv in enumerate(conversations_to_show):
                                st.write(f"**Conversation {i+1}** - {conv['message_count']} questions - ID: `{conv['id'][:12]}...`")
                                
                                col_info1, col_info2, col_info3 = st.columns(3)
                                with col_info1:
                                    st.write(f"⏱️ Durée: {conv['duration_minutes']:.0f}m")
                                with col_info2:
                                    st.write(f"📄 Usage docs: {conv['docs_usage_percentage']:.0f}%")
                                with col_info3:
                                    st.write(f"🎯 Pattern: {conv['conversation_pattern']}")
                                
                                if conv['model_switches'] > 0:
                                    st.write(f"🤖 Modèles utilisés: {', '.join(conv['models_used'])} ({conv['model_switches']} changements)")
                                else:
                                    st.write(f"🤖 Modèle unique: {conv['models_used'][0] if conv['models_used'] else 'N/A'}")
                                
                                # Option pour voir toutes les questions ou juste un aperçu
                                show_all_questions_key = f"show_all_q_{conv['id'][:8]}_{i}"
                                show_all_questions = st.checkbox(f"📝 Voir toutes les {len(conv['questions'])} questions", key=show_all_questions_key)
                                
                                if show_all_questions:
                                    st.write("**Toutes les questions :**")
                                    for j, q in enumerate(conv['questions'], 1):
                                        docs_icon = "📄" if q["has_docs"] else "🔍"
                                        timestamp_str = format_timestamp(q["timestamp"])
                                        st.write(f"   {j}. {docs_icon} {q['question']} *(Modèle: {q['modele']}, {timestamp_str})*")
                                        
                                        # Option pour voir la réponse de cette question spécifique
                                        show_response_long_key = f"show_response_long_{conv['id'][:8]}_{j}_{i}"
                                        if st.checkbox(f"💡 Voir la réponse #{j}", key=show_response_long_key):
                                            # Retrouver la réponse dans les conversations originales
                                            response_text = "Réponse non trouvée"
                                            for orig_conv in conversations:
                                                if orig_conv['id'] == conv['id']:
                                                    for msg in orig_conv['messages']:
                                                        # Chercher la question qui correspond (par timestamp ou contenu)
                                                        if (msg.get('timestamp') == q['timestamp'] or 
                                                            q['question'] in msg.get('question', '')):
                                                            response_text = msg.get('reponse', 'Réponse non disponible')
                                                            break
                                                    break
                                            
                                            if len(response_text) > 500:
                                                st.text_area(
                                                    f"Réponse #{j}:", 
                                                    response_text, 
                                                    height=200, 
                                                    disabled=True,
                                                    key=f"response_text_long_{conv['id'][:8]}_{j}_{i}"
                                                )
                                            else:
                                                st.write(f"**💡 Réponse #{j} :** {response_text}")
                                            st.write("")  # Espacement
                                else:
                                    # Aperçu des questions (3 premières)
                                    st.write("**Aperçu des questions :**")
                                    for j, q in enumerate(conv['questions'][:3], 1):
                                        docs_icon = "📄" if q["has_docs"] else "🔍"
                                        st.write(f"   {j}. {docs_icon} {q['question']}")
                                        
                                        # Option pour voir la réponse de cette question spécifique (aperçu)
                                        show_response_preview_key = f"show_response_preview_{conv['id'][:8]}_{j}_{i}"
                                        if st.checkbox(f"💡 Voir la réponse #{j}", key=show_response_preview_key):
                                            # Retrouver la réponse dans les conversations originales
                                            response_text = "Réponse non trouvée"
                                            for orig_conv in conversations:
                                                if orig_conv['id'] == conv['id']:
                                                    for msg in orig_conv['messages']:
                                                        # Chercher la question qui correspond (par timestamp ou contenu)
                                                        if (msg.get('timestamp') == q['timestamp'] or 
                                                            q['question'] in msg.get('question', '')):
                                                            response_text = msg.get('reponse', 'Réponse non disponible')
                                                            break
                                                    break
                                            
                                            if len(response_text) > 500:
                                                st.text_area(
                                                    f"Réponse #{j}:", 
                                                    response_text, 
                                                    height=200, 
                                                    disabled=True,
                                                    key=f"response_text_preview_{conv['id'][:8]}_{j}_{i}"
                                                )
                                            else:
                                                st.write(f"**💡 Réponse #{j} :** {response_text}")
                                            st.write("")  # Espacement
                                    
                                    if len(conv['questions']) > 3:
                                        st.write(f"   ... et {len(conv['questions']) - 3} autres questions")
                                
                                st.write("---")
                            
                            if not show_all and len(long_conv_analysis["conversations"]) > 10:
                                st.info(f"📋 Cochez 'Afficher toutes les conversations longues' pour voir les {len(long_conv_analysis['conversations']) - 10} autres conversations")
    
    with tab3:
        st.markdown("### 📈 Analyse des Modèles et Coûts")
        
        # Statistiques par modèle
        model_stats = get_model_stats(filtered_conversations)
        
        if model_stats:
            # Métriques globales (exclude gemini-2.0-flash-exp costs from total)
            total_model_cost = sum(stats['total_cost'] for k, stats in model_stats.items() if k != 'gemini-2.0-flash-exp')
            total_model_tokens = sum(stats['total_tokens'] for stats in model_stats.values())
            total_model_messages = sum(stats['count'] for stats in model_stats.values())
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("💰 Coût Total", f"${total_model_cost:.6f}")
            with col2:
                st.metric("🔤 Tokens Total", f"{total_model_tokens:,}")
            with col3:
                st.metric("📊 Messages Total", total_model_messages)
            
            # Graphique des coûts par modèle (exclude gemini-2.0-flash-exp from display)
            filtered_cost_data = {k: v for k, v in model_stats.items() if k != 'gemini-2.0-flash-exp'}
            if filtered_cost_data:
                fig_cost = px.bar(
                    x=list(filtered_cost_data.keys()),
                    y=[stats['total_cost'] for stats in filtered_cost_data.values()],
                    title="💰 Coût Total par Modèle",
                    labels={'x': 'Modèle', 'y': 'Coût ($)'},
                    color=[stats['total_cost'] for stats in filtered_cost_data.values()],
                    color_continuous_scale='viridis'
                )
                fig_cost.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_cost, use_container_width=True)
            
            # Graphique des tokens par modèle
            fig_tokens = px.bar(
                x=list(model_stats.keys()),
                y=[stats['total_tokens'] for stats in model_stats.values()],
                title="🔤 Tokens Total par Modèle",
                labels={'x': 'Modèle', 'y': 'Tokens'},
                color=[stats['total_tokens'] for stats in model_stats.values()],
                color_continuous_scale='plasma'
            )
            fig_tokens.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_tokens, use_container_width=True)
            
            # Tableau détaillé (exclude gemini-2.0-flash-exp costs from display)
            st.subheader("📊 Tableau Détaillé par Modèle")
            stats_df = pd.DataFrame([
                {
                    'Modèle': modele,
                    'Messages': stats['count'],
                    'Coût Total ($)': "N/A" if modele == 'gemini-2.0-flash-exp' else f"{stats['total_cost']:.6f}",
                    'Tokens Total': f"{stats['total_tokens']:,}",
                    'Coût Moyen ($)': "N/A" if modele == 'gemini-2.0-flash-exp' else f"{stats['avg_cost']:.6f}",
                    'Tokens Moyen': f"{stats['avg_tokens']:,}",
                    'Avec Documents': stats['with_docs'],
                    'Avec Citations': stats['with_citations']
                }
                for modele, stats in model_stats.items()
            ])
            
            st.dataframe(stats_df, use_container_width=True)
            
            # Timeline des coûts
            st.subheader("📈 Timeline des Coûts")
            
            timeline_data = []
            for conv in conversations:
                for msg in conv['messages']:
                    timestamp = msg.get('timestamp', 0)
                    model = msg.get('modele', 'unknown')
                    if timestamp:
                        date = format_date_only(timestamp)
                        # Exclude gemini-2.0-flash-exp costs from timeline display
                        cost = 0 if model == 'gemini-2.0-flash-exp' else msg.get('metadata', {}).get('cout', {}).get('prix', 0)
                        timeline_data.append({
                            'Date': date,
                            'Modèle': model,
                            'Coût': cost
                        })
            
            if timeline_data:
                timeline_df = pd.DataFrame(timeline_data)
                
                # Graphique timeline
                daily_stats = timeline_df.groupby(['Date', 'Modèle']).agg({
                    'Coût': 'sum'
                }).reset_index()
                
                fig_timeline = px.line(
                    daily_stats, 
                    x='Date', 
                    y='Coût', 
                    color='Modèle',
                    title="📈 Évolution des Coûts par Jour et Modèle",
                    markers=True
                )
                fig_timeline.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_timeline, use_container_width=True)
                
                # Graphique en barres par date
                daily_total = timeline_df.groupby('Date')['Coût'].sum().reset_index()
                fig_daily = px.bar(
                    daily_total,
                    x='Date',
                    y='Coût',
                    title="💰 Coût Total par Jour",
                    labels={'Date': 'Date', 'Coût': 'Coût ($)'}
                )
                fig_daily.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig_daily, use_container_width=True)
        else:
            st.warning("⚠️ Aucune donnée de modèle trouvée")

if __name__ == "__main__":
    main()
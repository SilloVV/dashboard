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
import redis
import pickle
from dotenv import load_dotenv

# Configuration du chemin pour les imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Charger les variables d'environnement
load_dotenv()

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

@st.cache_resource
def init_redis():
    """Initialise la connexion Redis Cloud"""
    try:
        # Configuration Redis Cloud depuis .env
        redis_host = os.getenv('REDIS_HOST', 'redis-16562.c339.eu-west-3-1.ec2.redns.redis-cloud.com')
        redis_port = int(os.getenv('REDIS_PORT', '16562'))
        redis_username = os.getenv('REDIS_USERNAME', '')
        redis_password = os.getenv('REDIS_PASSWORD', '')
        
        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            username=redis_username if redis_username else None,
            password=redis_password if redis_password else None,
            db=0,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        redis_client.ping()
        return redis_client
    except Exception as e:
        print(f"Erreur connexion Redis Cloud: {e}")
        # Redis n'est pas disponible, on continue sans cache
        return None

def get_from_cache(key):
    """Récupère des données du cache Redis (optionnel)"""
    redis_client = init_redis()
    if redis_client:
        try:
            data = redis_client.get(key)
            if data:
                return pickle.loads(data)
        except Exception as e:
            print(f"Erreur lecture cache: {e}")
    return None

def set_cache(key, data, ttl=300):
    """Sauvegarde des données dans le cache Redis (TTL en secondes, optionnel)"""
    redis_client = init_redis()
    if redis_client:
        try:
            redis_client.setex(key, ttl, pickle.dumps(data))
        except Exception as e:
            print(f"Erreur écriture cache: {e}")

@st.cache_data(ttl=60)
def load_conversations_from_firebase():
    """Charge toutes les conversations depuis Firebase avec cache"""
    firestore_db = init_firebase()
    if not firestore_db:
        return []
    
    conversations = []
    
    try:
        conversations_ref = firestore_db.collection('conversations')
        conversation_docs = conversations_ref.get()
        
        for conv_doc in conversation_docs:
            conv_id = conv_doc.id
            conv_data = conv_doc.to_dict()
            
            metadata = conv_data.get('metadata', {})
            
            messages_ref = conversations_ref.document(conv_id).collection('messages')
            message_docs = messages_ref.get()
            
            messages = []
            for msg_doc in message_docs:
                msg_data = msg_doc.to_dict()
                msg_data['id'] = msg_doc.id
                
                if 'timestamp' in msg_data and hasattr(msg_data['timestamp'], 'timestamp'):
                    msg_data['timestamp'] = msg_data['timestamp'].timestamp()
                
                messages.append(msg_data)
            
            messages.sort(key=lambda x: x.get('timestamp', 0))
            
            conversations.append({
                'id': conv_id,
                'conversation_id': conv_id,
                'metadata': metadata,
                'messages': messages
            })
        
        return conversations
        
    except Exception as e:
        st.error(f"❌ Erreur lors du chargement des conversations: {e}")
        return []

def get_summary_data():
    """Récupère les données de résumé avec cache Redis"""
    cache_key = "dashboard_summary"
    
    # Essayer de récupérer depuis le cache
    cached_data = get_from_cache(cache_key)
    if cached_data:
        return cached_data
    
    # Si pas de cache, récupérer depuis Firebase
    conversations = load_conversations_from_firebase()
    
    # Vérifier que les conversations sont valides
    if not conversations:
        return []
    
    # Calculer les statistiques de résumé
    summary_data = []
    email_stats = {}
    
    for conv in conversations:
        messages = conv.get('messages', [])
        if messages:
            for message in messages:
                if message and message.get('question', '').strip():
                    metadata = message.get('metadata', {})
                    email = None
                    
                    if metadata:
                        user_info = metadata.get('user_info', {})
                        if user_info and isinstance(user_info, dict):
                            email = user_info.get('user_email', '').strip().lower()
                        if not email:
                            email = metadata.get('email', '').strip().lower()
                    
                    if email:
                        if email not in email_stats:
                            email_stats[email] = {'nb_messages': 0, 'nb_conversations': set()}
                        
                        email_stats[email]['nb_messages'] += 1
                        conv_id = conv.get('conversation_id', conv.get('id', 'unknown'))
                        email_stats[email]['nb_conversations'].add(conv_id)
    
    # Convertir en format tableau
    for email, stats in email_stats.items():
        summary_data.append({
            'Mails': email,
            'nb de messages': stats['nb_messages'],
            'nb de conversation': len(stats['nb_conversations'])
        })
    
    # Trier par nombre de messages décroissant
    summary_data.sort(key=lambda x: x['nb de messages'], reverse=True)
    
    # Mettre en cache pour 10 minutes
    set_cache(cache_key, summary_data, 600)
    
    return summary_data

def main():
    """Fonction principale du dashboard avec système d'onglets"""
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
    
    # Système d'onglets
    tab1, tab2, tab3, tab4 = st.tabs(["🏠 Accueil", "📊 Analyse", "👥 Utilisations", "⭐ Feedbacks"])
    
    with tab1:
        accueil_tab()
    
    with tab2:
        analyse_tab()
    
    with tab3:
        utilisations_tab()
    
    with tab4:
        feedbacks_tab()

def accueil_tab():
    """Onglet Accueil avec tableau simple et cache Redis"""
    st.header("🏠 Tableau de bord principal")
    
    # Indicateur de cache
    redis_client = init_redis()
    cache_status = "🟢 Cache Redis actif" if redis_client else "🟡 Cache Redis indisponible"
    st.caption(cache_status)
    
    with st.spinner("🔄 Chargement des données..."):
        summary_data = get_summary_data()
    
    if summary_data:
        df = pd.DataFrame(summary_data)
        st.dataframe(df, use_container_width=True)
        
        # Affichage des métriques globales
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📧 Total Emails", len(summary_data))
        with col2:
            total_messages = sum(row['nb de messages'] for row in summary_data)
            st.metric("💬 Total Messages", total_messages)
        with col3:
            total_conversations = sum(row['nb de conversation'] for row in summary_data)
            st.metric("🗣️ Total Conversations", total_conversations)
    else:
        st.warning("⚠️ Aucune donnée trouvée")

def analyse_tab():
    """Onglet Analyse avec recherche, filtres et graphiques"""
    st.header("📊 Analyse des données")
    
    # Charger les emails disponibles pour le filtre
    conversations = load_conversations_from_firebase()
    emails = set()
    if conversations and len(conversations) > 0:
        for conv in conversations:
            messages = conv.get('messages', [])
            if messages:
                for message in messages:
                    if message and message.get('question', '').strip():
                        metadata = message.get('metadata', {})
                        if metadata:
                            user_info = metadata.get('user_info', {})
                            if user_info and isinstance(user_info, dict):
                                email = user_info.get('user_email', '').strip()
                                if email:
                                    emails.add(email)
                            # Fallback pour d'autres structures de métadonnées
                            email_fallback = metadata.get('email', '').strip()
                            if email_fallback:
                                emails.add(email_fallback)
    
    # Contrôles et filtres
    col1, col2 = st.columns(2)
    
    with col1:
        admin_filter = st.selectbox(
            "👤 Type d'utilisateur",
            ["Tous", "Admin exclusif", "Non admin exclusif"]
        )
    
    with col2:
        selected_email = st.selectbox(
            "📧 Filtrer par email",
            [""] + sorted(list(emails)) if emails else [""],
            format_func=lambda x: "Tous les emails" if x == "" else x,
            help=f"{len(emails)} emails disponibles" if emails else "Aucun email trouvé"
        )
    
    # Affichage conditionnel basé sur les filtres
    if admin_filter != "Tous" or selected_email:
        active_filters = []
        if admin_filter != "Tous":
            active_filters.append(f"Type='{admin_filter}'")
        if selected_email:
            active_filters.append(f"Email='{selected_email}'")
        
        st.info(f"🔍 Filtres actifs: {', '.join(active_filters)}")
        
        # Charger et filtrer les données
        with st.spinner("🔄 Analyse des données..."):
            conversations = load_conversations_from_firebase()
            
            if conversations:
                # Données pour les graphiques
                doc_per_message = []
                messages_per_conv = []
                questions_with_docs = {"Avec documents": 0, "Sans documents": 0}
                
                for conv in conversations:
                    message_count = 0
                    for message in conv.get('messages', []):
                        if message.get('question', '').strip():
                            metadata = message.get('metadata', {})
                            user_info = metadata.get('user_info', {})
                            user_id = user_info.get('user_id', 1)
                            
                            if admin_filter == "Admin exclusif" and user_id != 0:
                                continue
                            elif admin_filter == "Non admin exclusif" and user_id == 0:
                                continue
                            
                            # Filtre par email
                            if selected_email:
                                message_email = None
                                if metadata:
                                    if user_info and isinstance(user_info, dict):
                                        message_email = user_info.get('user_email', '').strip()
                                    if not message_email:
                                        message_email = metadata.get('email', '').strip()
                                
                                if message_email != selected_email:
                                    continue
                            
                            message_count += 1
                            
                            # Compter les documents
                            docs = message.get('docs', [])
                            docs_count = len(docs) if docs is not None and isinstance(docs, list) else 0
                            
                            if docs_count > 0:
                                doc_per_message.append(docs_count)
                                questions_with_docs["Avec documents"] += 1
                            else:
                                doc_per_message.append(0)
                                questions_with_docs["Sans documents"] += 1
                    
                    if message_count > 0:
                        messages_per_conv.append(message_count)
                
                # Graphiques en secteurs
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if doc_per_message:
                        doc_counts = Counter(doc_per_message)
                        fig1 = px.pie(
                            values=list(doc_counts.values()),
                            names=[f"{k} doc(s)" for k in doc_counts.keys()],
                            title="📄 Nb de documents par message"
                        )
                        st.plotly_chart(fig1, use_container_width=True)
                
                with col2:
                    if messages_per_conv:
                        msg_counts = Counter(messages_per_conv)
                        fig2 = px.pie(
                            values=list(msg_counts.values()),
                            names=[f"{k} message(s)" for k in msg_counts.keys()],
                            title="💬 Nb de messages par conversation"
                        )
                        st.plotly_chart(fig2, use_container_width=True)
                
                with col3:
                    if any(questions_with_docs.values()):
                        fig3 = px.pie(
                            values=list(questions_with_docs.values()),
                            names=list(questions_with_docs.keys()),
                            title="📎 Questions avec/sans documents"
                        )
                        st.plotly_chart(fig3, use_container_width=True)
            else:
                st.error("❌ Erreur lors du chargement des données")
    else:
        st.info("ℹ️ Veuillez sélectionner un type d'utilisateur ou choisir un email pour voir les analyses")

def feedbacks_tab():
    """Onglet Feedbacks avec camembert des ratings 1-5"""
    st.header("⭐ Analyse des Feedbacks")
    
    # Charger les emails disponibles
    conversations = load_conversations_from_firebase()
    emails = set()
    if conversations and len(conversations) > 0:
        for conv in conversations:
            messages = conv.get('messages', [])
            if messages:
                for message in messages:
                    if message and message.get('question', '').strip():
                        metadata = message.get('metadata', {})
                        if metadata:
                            user_info = metadata.get('user_info', {})
                            if user_info and isinstance(user_info, dict):
                                email = user_info.get('user_email', '').strip()
                                if email:
                                    emails.add(email)
                            email_fallback = metadata.get('email', '').strip()
                            if email_fallback:
                                emails.add(email_fallback)
    
    # Contrôles et filtres
    col1, col2 = st.columns(2)
    
    with col1:
        admin_filter = st.selectbox(
            "👤 Type d'utilisateur",
            ["Tous", "Admin exclusif", "Non admin exclusif"],
            key="feedback_admin_filter"
        )
    
    with col2:
        selected_email = st.selectbox(
            "📧 Filtrer par email",
            [""] + sorted(list(emails)) if emails else [""],
            format_func=lambda x: "Tous les emails" if x == "" else x,
            help=f"{len(emails)} emails disponibles" if emails else "Aucun email trouvé",
            key="feedback_email_filter"
        )
    
    # Affichage conditionnel basé sur les filtres
    if admin_filter != "Tous" or selected_email:
        active_filters = []
        if admin_filter != "Tous":
            active_filters.append(f"Type='{admin_filter}'")
        if selected_email:
            active_filters.append(f"Email='{selected_email}'")
        
        st.info(f"🔍 Filtres actifs: {', '.join(active_filters)}")
        
        # Charger et analyser les feedbacks
        with st.spinner("🔄 Analyse des feedbacks..."):
            feedback_data = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
            total_feedbacks = 0
            
            if conversations:
                for conv in conversations:
                    for message in conv.get('messages', []):
                        if message.get('question', '').strip() and message.get('feedback'):
                            metadata = message.get('metadata', {})
                            user_info = metadata.get('user_info', {})
                            user_id = user_info.get('user_id', 1)
                            
                            # Filtre admin
                            if admin_filter == "Admin exclusif" and user_id != 0:
                                continue
                            elif admin_filter == "Non admin exclusif" and user_id == 0:
                                continue
                            
                            # Filtre par email
                            if selected_email:
                                message_email = None
                                if metadata:
                                    if user_info and isinstance(user_info, dict):
                                        message_email = user_info.get('user_email', '').strip()
                                    if not message_email:
                                        message_email = metadata.get('email', '').strip()
                                
                                if message_email != selected_email:
                                    continue
                            
                            # Analyser le feedback
                            feedback = message.get('feedback', '')
                            if feedback and isinstance(feedback, str) and feedback.startswith('rating_'):
                                rating = feedback.replace('rating_', '')
                                if rating in feedback_data:
                                    feedback_data[rating] += 1
                                    total_feedbacks += 1
            
            # Affichage des résultats
            if total_feedbacks > 0:
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    # Camembert des ratings
                    ratings = [k for k, v in feedback_data.items() if v > 0]
                    counts = [v for v in feedback_data.values() if v > 0]
                    
                    if ratings:
                        fig = px.pie(
                            values=counts,
                            names=[f"{rating} étoile{'s' if rating != '1' else ''}" for rating in ratings],
                            title=f"⭐ Distribution des Ratings ({total_feedbacks} feedbacks)",
                            color_discrete_sequence=px.colors.qualitative.Set3
                        )
                        fig.update_traces(textposition='inside', textinfo='percent+label')
                        st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # Métriques détaillées
                    st.subheader("📊 Statistiques")
                    st.metric("Total Feedbacks", total_feedbacks)
                    
                    # Moyenne des ratings
                    if total_feedbacks > 0:
                        weighted_sum = sum(int(rating) * count for rating, count in feedback_data.items() if count > 0)
                        average_rating = weighted_sum / total_feedbacks
                        st.metric("Note Moyenne", f"{average_rating:.1f}/5")
                        
                        # Pourcentage de satisfaction (4-5 étoiles)
                        satisfaction = (feedback_data.get('4', 0) + feedback_data.get('5', 0)) / total_feedbacks * 100
                        st.metric("Satisfaction", f"{satisfaction:.1f}%")
                
                # Détail par rating avec boutons cliquables
                st.subheader("📋 Détail par Rating")
                
                # Variables de session pour gérer l'affichage
                if 'show_messages_for_rating' not in st.session_state:
                    st.session_state.show_messages_for_rating = None
                
                for rating in ['5', '4', '3', '2', '1']:
                    count = feedback_data.get(rating, 0)
                    if count > 0:
                        percentage = (count / total_feedbacks) * 100
                        col_rating, col_button = st.columns([3, 1])
                        
                        with col_rating:
                            st.write(f"⭐ {rating} étoile{'s' if rating != '1' else ''}: {count} ({percentage:.1f}%)")
                        
                        with col_button:
                            if st.button(f"Voir messages {rating}⭐", key=f"btn_rating_{rating}"):
                                if st.session_state.show_messages_for_rating == rating:
                                    st.session_state.show_messages_for_rating = None
                                else:
                                    st.session_state.show_messages_for_rating = rating
                
                # Affichage des messages filtrés par rating
                if st.session_state.show_messages_for_rating:
                    show_messages_by_rating(conversations, st.session_state.show_messages_for_rating, admin_filter, selected_email)
            
            else:
                st.warning("⚠️ Aucun feedback trouvé avec les filtres sélectionnés")
    else:
        st.info("ℹ️ Veuillez sélectionner un type d'utilisateur ou choisir un email pour voir les feedbacks")

def show_messages_by_rating(conversations, target_rating, admin_filter="Tous", selected_email=""):
    """Affiche tous les messages ayant un rating spécifique"""
    st.subheader(f"💬 Messages avec {target_rating} étoile{'s' if target_rating != '1' else ''}")
    
    matching_messages = []
    
    if conversations:
        for conv in conversations:
            conv_id = conv.get('conversation_id', conv.get('id', 'Unknown'))
            for message in conv.get('messages', []):
                if message.get('question', '').strip() and message.get('feedback'):
                    metadata = message.get('metadata', {})
                    user_info = metadata.get('user_info', {})
                    user_id = user_info.get('user_id', 1)
                    
                    # Filtres admin
                    if admin_filter == "Admin exclusif" and user_id != 0:
                        continue
                    elif admin_filter == "Non admin exclusif" and user_id == 0:
                        continue
                    
                    # Filtre par email
                    if selected_email:
                        message_email = None
                        if metadata:
                            if user_info and isinstance(user_info, dict):
                                message_email = user_info.get('user_email', '').strip()
                            if not message_email:
                                message_email = metadata.get('email', '').strip()
                        
                        if message_email != selected_email:
                            continue
                    
                    # Vérifier le rating
                    feedback = message.get('feedback', '')
                    if feedback and isinstance(feedback, str) and feedback.startswith('rating_'):
                        rating = feedback.replace('rating_', '')
                        if rating == target_rating:
                            # Récupérer l'email pour affichage
                            display_email = "Non spécifié"
                            if metadata:
                                if user_info and isinstance(user_info, dict):
                                    display_email = user_info.get('user_email', 'Non spécifié')
                                if display_email == "Non spécifié":
                                    display_email = metadata.get('email', 'Non spécifié')
                            
                            matching_messages.append({
                                'conversation_id': conv_id,
                                'question': message.get('question', ''),
                                'reponse': message.get('reponse', ''),
                                'timestamp': message.get('timestamp', ''),
                                'email': display_email,
                                'docs_count': len(message.get('docs', []) or []),
                                'feedback': feedback
                            })
    
    if matching_messages:
        st.success(f"✅ {len(matching_messages)} message(s) trouvé(s) avec {target_rating} étoile(s)")
        
        for i, msg in enumerate(matching_messages, 1):
            with st.expander(f"📧 Message {i} - {msg['email']} (Conv: {msg['conversation_id'][:8]}...)"):
                st.write("❓ **Question:**")
                st.write(msg['question'])
                
                # Informations sur le message
                col1, col2, col3 = st.columns(3)
                with col1:
                    stars = "⭐" * int(target_rating) + "☆" * (5 - int(target_rating))
                    st.caption(f"Rating: {stars} ({target_rating}/5)")
                with col2:
                    if msg['docs_count'] > 0:
                        st.caption(f"📄 {msg['docs_count']} document(s)")
                with col3:
                    if msg['timestamp']:
                        st.caption(f"⏰ {msg['timestamp']}")
                
                # Réponse (optionnelle)
                if msg['reponse']:
                    if st.button(f"👁️ Voir réponse", key=f"show_resp_{i}"):
                        st.write("💡 **Réponse:**")
                        st.markdown(f"<div style='background-color: #f0f2f6; padding: 10px; border-radius: 5px;'>{msg['reponse']}</div>", 
                                  unsafe_allow_html=True)
                else:
                    st.caption("ℹ️ Pas de réponse enregistrée")
    else:
        st.warning(f"⚠️ Aucun message trouvé avec {target_rating} étoile(s)")

def utilisations_tab():
    """Onglet Utilisations avec filtre par mail et liste des messages"""
    st.header("👥 Utilisation par utilisateur")
    
    # Charger les emails disponibles
    with st.spinner("🔄 Chargement des emails..."):
        conversations = load_conversations_from_firebase()
        
        emails = set()
        if conversations and len(conversations) > 0:
            for conv in conversations:
                messages = conv.get('messages', [])
                if messages:
                    for message in messages:
                        if message.get('question', '').strip():
                            metadata = message.get('metadata', {})
                            if metadata:
                                user_info = metadata.get('user_info', {})
                                if user_info and isinstance(user_info, dict):
                                    email = user_info.get('user_email', '').strip()
                                    if email:
                                        emails.add(email)
                                # Fallback pour d'autres structures de métadonnées
                                email_fallback = metadata.get('email', '').strip()
                                if email_fallback:
                                    emails.add(email_fallback)
    
    # Debug : afficher combien d'emails ont été trouvés
    st.info(f"📊 {len(emails)} emails trouvés dans les données")
    
    # Filtre par email
    if emails:
        selected_email = st.selectbox(
            "📧 Sélectionner un email",
            [""] + sorted(list(emails)),
            format_func=lambda x: "Choisir un email..." if x == "" else x
        )
        
        if selected_email:
            st.info(f"📧 Affichage des messages pour: {selected_email}")
            
            # Filtrer et afficher les messages
            user_messages = []
            
            if conversations:
                for conv in conversations:
                    if not conv:
                        continue
                    conv_messages = []
                    conv_id = conv.get('conversation_id', conv.get('id', 'Unknown'))
                    
                    messages = conv.get('messages', [])
                    if messages:
                        for message in messages:
                            if message and message.get('question', '').strip():
                                metadata = message.get('metadata', {})
                                email = None
                                
                                # Essayer plusieurs façons de récupérer l'email
                                if metadata:
                                    user_info = metadata.get('user_info', {})
                                    if user_info and isinstance(user_info, dict):
                                        email = user_info.get('user_email', '').strip()
                                    if not email:
                                        email = metadata.get('email', '').strip()
                                
                                if email and email == selected_email:
                                    docs = message.get('docs', [])
                                    docs_count = len(docs) if docs is not None else 0
                                    feedback = message.get('feedback', '')
                                    conv_messages.append({
                                        'question': message.get('question', ''),
                                        'reponse': message.get('reponse', ''),
                                        'timestamp': message.get('timestamp', ''),
                                        'docs_count': docs_count,
                                        'feedback': feedback
                                    })
                
                    if conv_messages:
                        user_messages.append({
                            'conversation_id': conv_id,
                            'messages': conv_messages
                        })
            
            # Affichage des conversations groupées
            if user_messages:
                for i, conv_data in enumerate(user_messages, 1):
                    # Calculer les statistiques de feedback pour la conversation
                    total_messages = len(conv_data['messages'])
                    messages_with_feedback = sum(1 for msg in conv_data['messages'] if msg.get('feedback'))
                    
                    # Créer l'indicateur pour le titre de la conversation
                    feedback_summary = f" ({messages_with_feedback}/{total_messages} feedbacks)" if messages_with_feedback > 0 else f" (0/{total_messages} feedbacks)"
                    
                    with st.expander(f"💬 Conversation {i}{feedback_summary} (ID: {conv_data['conversation_id']})"):
                        for j, msg in enumerate(conv_data['messages'], 1):
                            # Indicateur de feedback dans le titre
                            feedback_indicator = ""
                            if msg.get('feedback'):
                                if msg['feedback'].startswith('rating_'):
                                    rating = msg['feedback'].replace('rating_', '')
                                    feedback_indicator = f" ⭐ {rating}/5"
                                else:
                                    feedback_indicator = f" 👍 {msg['feedback']}"
                            
                            st.subheader(f"Question {j}{feedback_indicator}")
                            
                            # Affichage de la question (toujours visible)
                            st.write("❓ **Question:**")
                            st.write(msg['question'])
                            
                            # Informations complémentaires
                            col1, col2, col3 = st.columns([1, 1, 2])
                            with col1:
                                if msg['docs_count'] > 0:
                                    st.caption(f"📄 {msg['docs_count']} document(s)")
                                if msg['timestamp']:
                                    st.caption(f"⏰ {msg['timestamp']}")
                            
                            with col2:
                                # Affichage détaillé du feedback
                                if msg.get('feedback'):
                                    if msg['feedback'].startswith('rating_'):
                                        rating = int(msg['feedback'].replace('rating_', ''))
                                        stars = "⭐" * rating + "☆" * (5 - rating)
                                        st.caption(f"Feedback: {stars} ({rating}/5)")
                                    else:
                                        feedback_emoji = "👍" if msg['feedback'] == "good" else "👎" if msg['feedback'] == "bad" else "💬"
                                        st.caption(f"Feedback: {feedback_emoji} {msg['feedback']}")
                                else:
                                    st.caption("💭 Pas de feedback")
                            
                            # Toggle pour voir la réponse
                            with col3:
                                if msg['reponse']:
                                    show_response = st.button(
                                        "👁️ Voir la réponse", 
                                        key=f"show_response_{i}_{j}",
                                        help="Cliquer pour afficher/masquer la réponse"
                                    )
                                    
                                    if show_response:
                                        st.write("💡 **Réponse:**")
                                        with st.container():
                                            st.markdown(f"<div style='background-color: #f0f2f6; padding: 10px; border-radius: 5px;'>{msg['reponse']}</div>", 
                                                      unsafe_allow_html=True)
                                else:
                                    st.caption("ℹ️ Pas de réponse enregistrée")
                            
                            st.divider()
            else:
                st.warning(f"⚠️ Aucun message trouvé pour l'email: {selected_email}")
        else:
            st.info("ℹ️ Veuillez sélectionner un email pour voir ses messages")
    else:
        st.warning("⚠️ Aucun email trouvé dans les données")

if __name__ == "__main__":
    main()
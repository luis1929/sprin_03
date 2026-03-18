@app.route("/webhook", methods=["GET", "POST"])
@app.route("/webhook/evolution", methods=["GET", "POST"])
def webhook_evolution():
    if request.method == "GET":
        return jsonify({
            "status": "ok",
            "message": "Webhook endpoint activo. Usa POST para enviar eventos."
        }), 200

    data = request.get_json(silent=True) or {}
    logger.info(f"Webhook Evolution recibido: {data}")

    try:
        event_name = data.get("event", "")
        key_data = data.get("data", {}).get("key", {})
        message_data = data.get("data", {}).get("message", {})

        if key_data.get("fromMe") is True:
            return jsonify({"status": "ignored", "reason": "fromMe"}), 200

        mensaje = (
            message_data.get("conversation")
            or message_data.get("extendedTextMessage", {}).get("text")
            or message_data.get("imageMessage", {}).get("caption")
            or ""
        )

        remote_jid = key_data.get("remoteJid", "")
        numero = remote_jid.split("@")[0] if remote_jid else ""
        session_id = remote_jid or numero or str(uuid.uuid4())

        if not mensaje or not numero:
            return jsonify({"status": "invalid", "message": "No message or number found"}), 400

        user_id = None
        conversation_id = str(uuid.uuid4())
        database_mode = db_available()

        if database_mode:
            try:
                user = User.query.filter_by(phone_number=numero).first()
                if not user:
                    user = User(
                        id=str(uuid.uuid4()),
                        phone_number=numero,
                        channel="whatsapp",
                        status="active",
                        preferred_agent="general"
                    )
                    db.session.add(user)
                    db.session.flush()

                conv = Conversation.query.filter_by(
                    user_id=user.id,
                    status="active"
                ).order_by(desc(Conversation.started_at)).first()

                if not conv:
                    conv = Conversation(
                        id=conversation_id,
                        user_id=user.id,
                        agent_type=user.preferred_agent or "general",
                        status="active"
                    )
                    db.session.add(conv)
                    db.session.flush()
                else:
                    conversation_id = conv.id

                user_id = user.id

                msg_user = Message(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="user",
                    content=mensaje,
                    channel="whatsapp",
                    processed_by="evolution",
                    meta_data={
                        "event": event_name,
                        "remote_jid": remote_jid
                    }
                )
                db.session.add(msg_user)
                safe_commit()

            except Exception as e:
                db.session.rollback()
                database_mode = False
                logger.warning(f"Fallo persistencia, sigo sin DB: {str(e)}")

        respuesta = consultar_flowise(mensaje, session_id)
        evolution_status = enviar_mensaje_evolution(numero, respuesta)

        if database_mode and user_id:
            try:
                msg_agent = Message(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="agent",
                    content=respuesta,
                    channel="whatsapp",
                    processed_by="flowise"
                )
                db.session.add(msg_agent)

                user = db.session.get(User, user_id)
                if user:
                    user.last_interaction = datetime.utcnow()

                safe_commit()

            except Exception as e:
                db.session.rollback()
                logger.warning(f"No se pudo guardar respuesta del agente: {str(e)}")

        log_audit_event("webhook_evolution_processed", user_id, {
            "conversation_id": conversation_id,
            "message_preview": mensaje[:100],
            "remote_jid": remote_jid,
            "database_mode": database_mode,
            "evolution_status": evolution_status
        })

        return jsonify({
            "status": "success",
            "mode": "normal" if database_mode else "degraded",
            "database_persisted": database_mode,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "reply_preview": respuesta[:120]
        }), 200

    except Exception as e:
        logger.error(f"Error en webhook_evolution: {str(e)}")
        log_audit_event("webhook_evolution_error", data={"error": str(e)})
        return jsonify({"status": "error", "message": str(e)}), 500

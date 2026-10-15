from servicios.datos_padron import ServicioDatosPadron


def test_gestion_lectores_del_padron_delega_a_firebase_auth(monkeypatch):
    llamadas = []

    class ServicioFirebaseFalso:
        def listar_lectores(self):
            llamadas.append(("listar",))
            return [{"uid": "firebase-uid", "email": "bryanlaricoro28@gmail.com"}]

        def crear_lector(self, email, password, display_name=None):
            llamadas.append(("crear", email, password, display_name))
            return {"uid": "nuevo-uid", "email": email}

        def actualizar_lector(
            self, uid, display_name=None, password=None, disabled=None
        ):
            llamadas.append(
                ("actualizar", uid, display_name, password, disabled)
            )
            return {"uid": uid, "disabled": disabled}

        def eliminar_lector(self, uid):
            llamadas.append(("eliminar", uid))

    monkeypatch.setattr(
        "servicios.datos.ServicioDatosFirebase", ServicioFirebaseFalso
    )
    servicio = ServicioDatosPadron.__new__(ServicioDatosPadron)
    servicio.config = {"lectores": ["AYACUCHO"]}

    assert servicio.listar_lectores() == [
        {"uid": "firebase-uid", "email": "bryanlaricoro28@gmail.com"}
    ]
    assert servicio.crear_lector(
        "bryanlaricoro28@gmail.com", "secreto", "Bryan"
    ) == {"uid": "nuevo-uid", "email": "bryanlaricoro28@gmail.com"}
    assert servicio.actualizar_lector(
        "firebase-uid", display_name="Bryan", disabled=True
    ) == {"uid": "firebase-uid", "disabled": True}
    servicio.eliminar_lector("firebase-uid")

    assert llamadas == [
        ("listar",),
        ("crear", "bryanlaricoro28@gmail.com", "secreto", "Bryan"),
        ("actualizar", "firebase-uid", "Bryan", None, True),
        ("eliminar", "firebase-uid"),
    ]
    assert servicio.config == {"lectores": ["AYACUCHO"]}

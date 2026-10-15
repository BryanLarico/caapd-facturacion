package com.caapd.lecturas

import android.app.Application
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.FirebaseFirestoreSettings

/**
 * Application personalizado para habilitar la caché offline de Firestore.
 * Esto permite que la app cargue y guarde datos sin internet.
 */
class LecturasApp : Application() {
    override fun onCreate() {
        super.onCreate()

        val settings = FirebaseFirestoreSettings.Builder()
            .setPersistenceEnabled(true)            // caché local persistente
            .setCacheSizeBytes(FirebaseFirestoreSettings.CACHE_SIZE_UNLIMITED)
            .build()

        FirebaseFirestore.getInstance().firestoreSettings = settings
    }
}

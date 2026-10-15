/* main.js — JavaScript mínimo y vanilla. Solo lo imprescindible. */

/* -------------------------------------------------------------------
   Pestañas (tabs)
   Activa la pestaña clicada y muestra su contenido.
   ------------------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', function () {

    // Pestañas
    document.querySelectorAll('.pestana').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var grupo = btn.closest('.pestanas-contenedor') || btn.parentElement.parentElement;
            // Desactivar todas las pestañas del mismo grupo
            grupo.querySelectorAll('.pestana').forEach(function (b) {
                b.classList.remove('activa');
                b.setAttribute('aria-selected', 'false');
            });
            // Ocultar todos los contenidos
            grupo.querySelectorAll('.contenido-pestana').forEach(function (c) {
                c.classList.remove('activo');
            });
            // Activar la pestaña clicada
            btn.classList.add('activa');
            btn.setAttribute('aria-selected', 'true');
            var target = document.getElementById(btn.dataset.target);
            if (target) {
                target.classList.add('activo');
            }
        });
    });

    // Activar la primera pestaña de cada grupo al cargar
    document.querySelectorAll('.pestanas').forEach(function (grupo) {
        var primera = grupo.querySelector('.pestana');
        if (primera && !grupo.querySelector('.pestana.activa')) {
            primera.click();
        }
    });

    /* -----------------------------------------------------------------
       Buscador en tablas (filtro en memoria, sin Firebase)
       El campo de búsqueda debe tener data-tabla="id-de-la-tabla"
       ----------------------------------------------------------------- */
    document.querySelectorAll('.campo-buscar').forEach(function (input) {
        var tablaId = input.dataset.tabla;
        var tabla = document.getElementById(tablaId);
        if (!tabla) return;

        input.addEventListener('input', function () {
            var texto = input.value.toLowerCase().trim();
            tabla.querySelectorAll('tbody tr').forEach(function (fila) {
                var contenido = fila.textContent.toLowerCase();
                fila.style.display = contenido.includes(texto) ? '' : 'none';
            });
        });
    });

    /* -----------------------------------------------------------------
       Confirmación antes de acciones destructivas
       Botones con data-confirmar="Mensaje de confirmación"
       ----------------------------------------------------------------- */
    document.querySelectorAll('[data-confirmar]').forEach(function (el) {
        el.addEventListener('click', function (e) {
            var mensaje = el.dataset.confirmar || '¿Estás seguro?';
            if (!confirm(mensaje)) {
                e.preventDefault();
            }
        });
    });

    /* -----------------------------------------------------------------
       Cierre automático de alertas (opcional: data-autocerrar="3000")
       ----------------------------------------------------------------- */
    document.querySelectorAll('.alerta[data-autocerrar]').forEach(function (alerta) {
        var ms = parseInt(alerta.dataset.autocerrar, 10) || 4000;
        setTimeout(function () {
            alerta.style.transition = 'opacity 0.5s';
            alerta.style.opacity = '0';
            setTimeout(function () { alerta.remove(); }, 500);
        }, ms);
    });

});

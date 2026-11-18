/* Comunicación con el API Gateway de TiendaIA.
Todo el cliente web habla con el backend SOLO a través de este archivo:
si cambia la dirección del gateway o se agrega autenticación (Lab. 6),
se ajusta aquí y no en cada pantalla. */
// ------------------------------------------------------------ Configuración
// localStorage guarda datos en el navegador (sobreviven a recargar la página).
// Se envuelve en try/catch porque algunos navegadores lo bloquean.
function leerAjuste(clave, porOmision) {
try {
return localStorage.getItem(clave) || porOmision;
} catch (e) {
return porOmision;
}
}
function guardarAjuste(clave, valor) {
try {
if (valor) localStorage.setItem(clave, valor);
else localStorage.removeItem(clave);
} catch (e) { /* sin almacenamiento: el ajuste dura solo esta visita */ }
}
// Error con el código HTTP, para mostrar mensajes claros (404, 422, 502...)
class ErrorApi extends Error {
constructor(estado, detalle) {
super(`HTTP ${estado}: ${detalle}`);
this.estado = estado;
}
}
const Api = {
// URL del gateway sin "/" al final, p. ej. http://localhost:8080
base() {
return leerAjuste("tiendaia_api", "http://localhost:8080").replace(/\/+$/, "");
},
fijarBase(url) { guardarAjuste("tiendaia_api", url.trim()); },
// Token JWT (Laboratorio 6). Mientras no exista, las peticiones van sin él.
token() { return leerAjuste("tiendaia_token", ""); },
fijarToken(t) { guardarAjuste("tiendaia_token", t); },
/* Hace una petición al gateway y devuelve el JSON de la respuesta.
- metodo: "GET", "POST", "PUT" o "DELETE"
- ruta: por ejemplo "/api/clientes"
- cuerpo: objeto (se envía como JSON) o FormData (archivos, Lab. 4)
Lanza ErrorApi si el servidor responde con un código de error. */
async pedir(metodo, ruta, cuerpo) {
const opciones = { method: metodo, headers: {} };
if (cuerpo instanceof FormData) {
// Con FormData el navegador arma el multipart y su Content-Type solo
opciones.body = cuerpo;
} else if (cuerpo !== undefined) {
opciones.headers["Content-Type"] = "application/json";
opciones.body = JSON.stringify(cuerpo); // objeto de JS -> texto JSON
}
const token = this.token();
if (token) opciones.headers["Authorization"] = `Bearer ${token}`;
let resp;
try {
// fetch envía la petición HTTP; await espera la respuesta sin congelar la página
resp = await fetch(this.base() + ruta, opciones);
} catch (e) {
// Sin respuesta: gateway apagado, URL mal escrita o CORS no permitido
throw new ErrorApi(0, "no hubo respuesta del gateway (¿URL correcta? ¿CORS?)");
}
if (resp.status === 204) return null; // 204 No Content: sin cuerpo
const texto = await resp.text();
let datos = null;
try { datos = texto ? JSON.parse(texto) : null; } catch (e) { datos = texto; }
if (!resp.ok) {
// FastAPI manda el motivo en "detail" (texto o lista de errores de validación)
let detalle = datos && datos.detail !== undefined ? datos.detail : texto;
if (Array.isArray(detalle)) detalle = detalle.map(d => d.msg).join("; ");
throw new ErrorApi(resp.status, detalle || resp.statusText);
}
return datos;
},
// Atajos para cada método HTTP
get(ruta) { return this.pedir("GET", ruta); },
post(ruta, cuerpo) { return this.pedir("POST", ruta, cuerpo); },
put(ruta, cuerpo) { return this.pedir("PUT", ruta, cuerpo); },
borrar(ruta) { return this.pedir("DELETE", ruta); },
};
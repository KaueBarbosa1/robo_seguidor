export class Dados {
  constructor(erro) {
    this.estado = null;
    this.erro = erro;
    this.token = "";
    this.parado = false;
  }
  async get(url) {
    const r = await fetch(url, { cache: "no-store" });
    const d = await r.json();
    if (!r.ok) throw Error(d.erro ?? r.statusText);
    return d;
  }
  async post(url, d) {
    const r = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Gemeo-Token": this.token,
      },
      body: JSON.stringify(d),
    });
    const q = await r.json();
    if (!r.ok) throw Error(q.erro ?? r.statusText);
    return q;
  }
  async iniciar(onEstado) {
    this.config = await this.get("/api/config");
    this.token = this.config.token;
    this.timer = setInterval(async () => {
      if (this.ocupado) return;
      this.ocupado = true;
      try {
        const s = await this.get("/api/estado");
        s.recebido = performance.now();
        this.estado = s;
        onEstado(s);
      } catch (e) {
        if (this.estado) {
          this.estado.dados.disponivel = false;
          onEstado(this.estado);
        }
        this.erro(e);
      } finally {
        this.ocupado = false;
      }
    }, 100);
    return this.config;
  }
}

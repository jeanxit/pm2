document.addEventListener("DOMContentLoaded", function () {
  // Tooltips Bootstrap
  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.map(el => new bootstrap.Tooltip(el));

  // Modal: abrir se existir
  const resultadoModal = document.getElementById('resultadoModal');
  if (resultadoModal) {
    const modal = new bootstrap.Modal(resultadoModal);
    modal.show();
  }

  // Alternância dos campos do formulário
  const acao = document.getElementById("acao");
  const campoDirProjeto = document.getElementById("campo-dir-projeto");
  const campoNome = document.getElementById("campo-nome");

  function toggleCampos() {
    const valor = acao.value;
    if (valor === "start") {
      campoDirProjeto.style.display = "";
      campoNome.style.display = "none";
      document.getElementById("nome").value = "";
    } else if (valor === "restart") {
      campoDirProjeto.style.display = "";
      campoNome.style.display = "";
    } else if (["stop", "delete"].includes(valor)) {
      campoDirProjeto.style.display = "none";
      campoNome.style.display = "";
      document.getElementById("dir_projeto").value = "";
    } else {
      campoDirProjeto.style.display = "none";
      campoNome.style.display = "none";
    }
  }

  acao.addEventListener("change", toggleCampos);
  toggleCampos();

  // Ativar botões de ação PM2
  function ativaAcoesPM2() {
    document.querySelectorAll('.btn-acao').forEach(btn => {
      btn.addEventListener('click', function () {
        const nome = this.getAttribute('data-nome');
        const acao = this.getAttribute('data-acao');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        fetch("/acao_pm2", {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ nome, acao })
        })
          .then(r => r.json())
          .then(resp => {
            setTimeout(atualizarTabelaEGrafico, 800);
          })
          .catch(err => {
            console.error("❌ Erro na ação PM2:", err);
            alert("Erro ao executar ação: " + err.message);
          });
      });
    });
  }

  // Atualizar tabela e gráfico
  function atualizarTabelaEGrafico() {
    console.log("🔄 Atualizando dados do PM2...");
    fetch("/tabela_pm2")
      .then(res => {
        if (!res.ok) throw new Error("Resposta não OK da API.");
        return res.json();
      })
      .then(data => {
        console.log("✅ Dados recebidos:", data);
        const tabela = document.getElementById("tabela-pm2");
        if (data?.tabela_html && tabela) {
          tabela.innerHTML = data.tabela_html;
        } else if (tabela) {
          tabela.innerHTML = '<div class="alert alert-danger mt-4">Não foi possível carregar os dados do PM2.</div>';
        }

        // Reativa tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(el => new bootstrap.Tooltip(el));

        // Reativa botões
        ativaAcoesPM2();

        // Atualiza gráfico
        if (window.statusChart && data.status_counts) {
          window.statusChart.data.datasets[0].data = [
            data.status_counts.online,
            data.status_counts.stopped,
            data.status_counts.errored,
            data.status_counts.paused,
            data.status_counts.unknown
          ];
          window.statusChart.update();
        }
      })
      .catch((err) => {
        console.error("❌ Erro ao buscar dados da tabela:", err);
        // Não mostra mais alert!
      })
      .finally(() => {
        // Sempre remove o preloader, mesmo em erro
        const preloader = document.getElementById("preloader");
        if (preloader) {
          preloader.style.opacity = "0";
          preloader.style.transition = "opacity 0.4s ease";
          setTimeout(() => preloader.style.display = "none", 400);
        }
      });
  }

  // Atualiza automaticamente a cada 10s
  setInterval(atualizarTabelaEGrafico, 10000);

  // Primeira carga
  atualizarTabelaEGrafico();
  ativaAcoesPM2();
});

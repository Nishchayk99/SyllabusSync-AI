(() => {
  const fields = ['syllabus', 'notes', 'pyq'];
  fields.forEach((name) => {
    const input = document.getElementById(name);
    const zone = document.getElementById(`zone-${name}`);
    const selected = document.getElementById(`selected-${name}`);
    if (!input || !zone || !selected) return;
    const showFile = (file) => {
      if (!file) { selected.classList.remove('has-file'); selected.querySelector('.filename').textContent = 'No file selected'; return; }
      selected.classList.add('has-file');
      selected.querySelector('.filename').textContent = `${file.name} · ${(file.size / (1024 * 1024)).toFixed(2)} MB`;
      zone.querySelector('b').textContent = 'PDF selected — click to replace';
      zone.querySelector('small').textContent = 'Ready for analysis';
    };
    input.addEventListener('change', () => showFile(input.files[0]));
    ['dragenter', 'dragover'].forEach(eventName => zone.addEventListener(eventName, e => { e.preventDefault(); zone.classList.add('dragover'); }));
    ['dragleave', 'drop'].forEach(eventName => zone.addEventListener(eventName, e => { e.preventDefault(); zone.classList.remove('dragover'); }));
    zone.addEventListener('drop', e => {
      const file = e.dataTransfer.files[0];
      if (file && (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'))) {
        const transfer = new DataTransfer(); transfer.items.add(file); input.files = transfer.files; showFile(file);
      } else { zone.querySelector('small').textContent = 'Please drop a PDF file'; }
    });
  });
  const form = document.getElementById('uploadForm');
  if (form) form.addEventListener('submit', e => {
    for (const name of fields) {
      const input = document.getElementById(name);
      if (!input || !input.files.length) { e.preventDefault(); input?.reportValidity(); return; }
      if (input.files[0].size > 25 * 1024 * 1024) { e.preventDefault(); alert(`${input.files[0].name} is larger than 25 MB.`); return; }
    }
    const btn = document.getElementById('submitBtn');
    if (btn) { btn.disabled = true; btn.querySelector('span:first-child').textContent = 'Analysing…'; }
    document.getElementById('loadingOverlay')?.classList.add('visible');
  });

  const search = document.getElementById('topicSearch');
  const statusFilter = document.getElementById('statusFilter');
  const priorityFilter = document.getElementById('priorityFilter');
  const rows = Array.from(document.querySelectorAll('.topic-row'));
  const empty = document.getElementById('emptyState');
  const rowCount = document.getElementById('rowCount');
  function filterRows() {
    const q = (search?.value || '').trim().toLowerCase();
    const status = statusFilter?.value || 'all';
    const priority = priorityFilter?.value || 'all';
    let shown = 0;
    rows.forEach(row => {
      const visible = row.dataset.topic.includes(q) && (status === 'all' || row.dataset.status === status) && (priority === 'all' || row.dataset.priority === priority);
      row.hidden = !visible;
      if (visible) shown++;
    });
    if (empty) empty.hidden = shown !== 0;
    if (rowCount) rowCount.textContent = `Showing ${shown} of ${rows.length} topics`;
  }
  [search, statusFilter, priorityFilter].forEach(el => el?.addEventListener('input', filterRows));
  document.querySelectorAll('.expand-btn').forEach(btn => btn.addEventListener('click', () => {
    const row = btn.closest('.topic-row');
    if (!row) return;
    const expanded = row.classList.toggle('expanded');
    btn.setAttribute('aria-expanded', String(expanded));
    btn.textContent = expanded ? '−' : '＋';
  }));
})();

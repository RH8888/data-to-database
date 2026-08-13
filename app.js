const UNKNOWN = 'نامشخص';
const state = { raw: null, courses: [], filtered: [], selectedCourse: null, debounce: 0 };
const els = {
  search: document.querySelector('#searchInput'), teacher: document.querySelector('#teacherFilter'), subject: document.querySelector('#subjectFilter'),
  course: document.querySelector('#courseFilter'), year: document.querySelector('#yearFilter'), provider: document.querySelector('#providerFilter'),
  clear: document.querySelector('#clearFilters'), stats: document.querySelector('#stats'), summary: document.querySelector('#resultSummary'),
  insight: document.querySelector('#teacherSubjectInsight'), results: document.querySelector('#results'), courseView: document.querySelector('#courseView'),
  back: document.querySelector('#backButton'), template: document.querySelector('#courseCardTemplate')
};

const normalize = value => String(value ?? '').trim().replace(/[ي]/g, 'ی').replace(/[ك]/g, 'ک').toLocaleLowerCase('fa-IR');
const valueOrUnknown = value => String(value ?? '').trim() || UNKNOWN;
const unique = values => [...new Set(values.map(valueOrUnknown))].sort((a,b)=>a.localeCompare(b,'fa'));
const countVideos = course => (course.video_urls || course.videos || []).length;
const courseProviders = course => unique((course.video_urls || []).map(v => v?.provider).filter(Boolean));

function adaptCourse(course, index) {
  const sessions = Array.isArray(course.sessions) ? course.sessions : [];
  const videos = Array.isArray(course.video_urls) ? course.video_urls : [];
  const providers = courseProviders(course);
  const searchText = normalize([
    course.subject, course.teacher, course.course_name, course.program_year, providers.join(' '),
    ...sessions.flatMap(s => [s.heading, s.title]), ...videos.map(v => v.url)
  ].join(' '));
  return { ...course, _id: index, _subject: valueOrUnknown(course.subject), _teacher: valueOrUnknown(course.teacher),
    _name: valueOrUnknown(course.course_name), _year: valueOrUnknown(course.program_year), _providers: providers.length ? providers : [UNKNOWN],
    _sessions: sessions, _videos: videos, _searchText: searchText };
}

async function init() {
  try {
    state.raw = await loadCourseData();
    const courses = Array.isArray(state.raw) ? state.raw : state.raw.courses;
    if (!Array.isArray(courses)) throw new Error('courses.json does not contain a courses array.');
    state.courses = courses.map(adaptCourse);
    populateFilters();
    bindEvents();
    applyFilters();
  } catch (error) {
    els.summary.textContent = 'خطا در بارگذاری اطلاعات دوره‌ها';
    els.results.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function loadCourseData() {
  if (window.COURSES_DATA) return window.COURSES_DATA;

  try {
    const response = await fetch('courses.json');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  } catch (error) {
    if (window.location.protocol === 'file:') {
      throw new Error('مرورگر اجازه خواندن courses.json با آدرس file:// را نمی‌دهد. فایل index.html را از طریق یک سرور محلی باز کنید یا courses-data.js را کنار آن نگه دارید.');
    }
    throw error;
  }
}

function populateFilters() {
  fillSelect(els.teacher, unique(state.courses.map(c => c._teacher)));
  fillSelect(els.subject, unique(state.courses.map(c => c._subject)));
  fillSelect(els.course, unique(state.courses.map(c => c._name)));
  fillSelect(els.year, unique(state.courses.map(c => c._year)));
  fillSelect(els.provider, unique(state.courses.flatMap(c => c._providers)));
  const videos = state.courses.reduce((sum, c) => sum + countVideos(c), 0);
  const sessions = state.courses.reduce((sum, c) => sum + c._sessions.length, 0);
  const noSessionsWithVideos = state.courses.filter(c => !c._sessions.length && countVideos(c)).length;
  els.stats.innerHTML = `<strong>${state.courses.length.toLocaleString('fa-IR')}</strong> دوره<br><strong>${sessions.toLocaleString('fa-IR')}</strong> جلسه<br><strong>${videos.toLocaleString('fa-IR')}</strong> لینک ویدئو<br>${noSessionsWithVideos.toLocaleString('fa-IR')} دوره دارای ویدئو بدون جلسه`;
}
function fillSelect(select, values) { values.forEach(value => select.add(new Option(value, value))); }
function bindEvents() {
  [els.teacher, els.subject, els.course, els.year, els.provider].forEach(el => el.addEventListener('change', applyFilters));
  els.search.addEventListener('input', () => { clearTimeout(state.debounce); state.debounce = setTimeout(applyFilters, 120); });
  els.clear.addEventListener('click', () => { els.search.value = ''; [els.teacher,els.subject,els.course,els.year,els.provider].forEach(el => el.value=''); applyFilters(); });
  els.back.addEventListener('click', () => showResults());
}
function applyFilters() {
  const query = normalize(els.search.value);
  state.filtered = state.courses.filter(c => (!query || c._searchText.includes(query)) && matches(c, '_teacher', els.teacher.value) && matches(c, '_subject', els.subject.value) && matches(c, '_name', els.course.value) && matches(c, '_year', els.year.value) && (!els.provider.value || c._providers.includes(els.provider.value)));
  renderResults(); showResults();
}
const matches = (course, key, selected) => !selected || course[key] === selected;
function renderResults() {
  els.summary.textContent = `${state.filtered.length.toLocaleString('fa-IR')} دوره از ${state.courses.length.toLocaleString('fa-IR')} دوره نمایش داده شده است.`;
  const teacherCount = unique(state.filtered.map(c => c._teacher)).length;
  const subjectCount = unique(state.filtered.map(c => c._subject)).length;
  els.insight.innerHTML = `در این نتیجه <strong>${teacherCount.toLocaleString('fa-IR')}</strong> مدرس و <strong>${subjectCount.toLocaleString('fa-IR')}</strong> درس دیده می‌شود.`;
  els.results.innerHTML = '';
  if (!state.filtered.length) { els.results.innerHTML = '<div class="empty">دوره‌ای با این جستجو یا فیلتر پیدا نشد.</div>'; return; }
  const frag = document.createDocumentFragment();
  state.filtered.forEach(course => {
    const node = els.template.content.cloneNode(true);
    node.querySelector('.subject').textContent = course._subject; node.querySelector('.year').textContent = course._year;
    node.querySelector('h3').textContent = course._name; node.querySelector('.teacher').textContent = course._teacher;
    node.querySelector('.meta').textContent = course._providers.join('، ');
    node.querySelector('.counts').textContent = `${course._sessions.length.toLocaleString('fa-IR')} جلسه · ${countVideos(course).toLocaleString('fa-IR')} ویدئو`;
    node.querySelector('button').addEventListener('click', () => openCourse(course._id)); frag.append(node);
  });
  els.results.append(frag);
}
function openCourse(id) { renderCourse(state.courses.find(c => c._id === id)); els.results.classList.add('hidden'); els.courseView.classList.remove('hidden'); els.back.classList.remove('hidden'); window.scrollTo({top:0,behavior:'smooth'}); }
function showResults() { els.courseView.classList.add('hidden'); els.results.classList.remove('hidden'); els.back.classList.add('hidden'); }
function renderCourse(course) {
  const videosByMessage = new Map(); course._videos.forEach(v => { const k = v?.message_id ?? 'unknown'; if (!videosByMessage.has(k)) videosByMessage.set(k, []); videosByMessage.get(k).push(v); });
  const used = new Set();
  const sessionsHtml = course._sessions.map((s, i) => { const vids = videosByMessage.get(s.message_id) || []; vids.forEach(v => used.add(v)); return `<section class="session"><h3>${escapeHtml(s.heading || s.title || `جلسه ${i + 1}`)}</h3><p>${escapeHtml(s.title || UNKNOWN)}</p>${videoLinks(vids)}</section>`; }).join('');
  const otherVideos = course._videos.filter(v => !used.has(v));
  els.courseView.innerHTML = `<div class="course-head"><h2>${escapeHtml(course._name)}</h2><div class="kv"><span>مدرس: ${escapeHtml(course._teacher)}</span><span>درس: ${escapeHtml(course._subject)}</span><span>سال: ${escapeHtml(course._year)}</span><span>ارائه‌دهنده: ${escapeHtml(course._providers.join('، '))}</span><span>${course._sessions.length.toLocaleString('fa-IR')} جلسه</span><span>${countVideos(course).toLocaleString('fa-IR')} ویدئو</span></div></div>${sessionsHtml || '<div class="empty">برای این دوره جلسه‌ای ثبت نشده است.</div>'}${otherVideos.length ? `<section class="session"><h3>ویدئوهای دیگر</h3>${videoLinks(otherVideos)}</section>` : ''}`;
}
function videoLinks(videos) { return videos.length ? `<div class="videos">${videos.map((v,i)=>`<a href="${escapeAttr(v.url)}" target="_blank" rel="noopener noreferrer">ویدئو ${(i+1).toLocaleString('fa-IR')} · ${escapeHtml(v.provider || UNKNOWN)}</a>`).join('')}</div>` : '<p>لینک ویدئویی برای این جلسه ثبت نشده است.</p>'; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch])); }
function escapeAttr(value) { return escapeHtml(value).replace(/'/g, '&#39;'); }
init();

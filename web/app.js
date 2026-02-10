// Variables globales
let planningData = null;
let currentDate = 0;

// Éléments DOM
const uploadSection = document.getElementById('uploadSection');
const scheduleSection = document.getElementById('scheduleSection');
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const newFileBtn = document.getElementById('newFileBtn');
const dateTabs = document.getElementById('dateTabs');
const scheduleContainer = document.getElementById('scheduleContainer');

// Métriques
const totalDefensesEl = document.getElementById('totalDefenses');
const avgDefensesEl = document.getElementById('avgDefenses');
const maxDefensesEl = document.getElementById('maxDefenses');
const minDefensesEl = document.getElementById('minDefenses');

// Navbar scroll behavior
let lastScrollTop = 0;
const header = document.querySelector('.header');

// Créneaux horaires (exemple de mapping)
const timeSlots = [
    '08h00 - 09h00',
    '09h00 - 10h00',
    '10h00 - 11h00',
    '11h00 - 12h00',
    '14h00 - 15h00',
    '15h00 - 16h00',
    '16h00 - 17h00',
    '17h00 - 18h00'
];

// Initialisation
document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
    initializeNavbarScroll();
});

function initializeEventListeners() {
    // Clic sur la zone d'upload
    uploadArea.addEventListener('click', () => {
        fileInput.click();
    });

    // Changement de fichier
    fileInput.addEventListener('change', handleFileSelect);

    // Drag and drop
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);

    // Nouveau fichier
    newFileBtn.addEventListener('click', resetToUpload);
}

function initializeNavbarScroll() {
    window.addEventListener('scroll', () => {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

        if (scrollTop > lastScrollTop && scrollTop > 100) {
            // Scrolling down
            header.style.transform = 'translateY(-100%)';
        } else {
            // Scrolling up
            header.style.transform = 'translateY(0)';
        }

        lastScrollTop = scrollTop <= 0 ? 0 : scrollTop;
    });
}

function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    uploadArea.classList.add('drag-over');
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    uploadArea.classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    uploadArea.classList.remove('drag-over');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        processFile(files[0]);
    }
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        processFile(files[0]);
    }
}

function processFile(file) {
    if (!file.name.endsWith('.json')) {
        alert('Veuillez sélectionner un fichier JSON.');
        return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            planningData = JSON.parse(e.target.result);
            displaySchedule();
        } catch (error) {
            alert('Erreur lors de la lecture du fichier JSON. Vérifiez le format.');
            console.error(error);
        }
    };
    reader.readAsText(file);
}

function displaySchedule() {
    // Afficher la section planning
    uploadSection.hidden = false;
    scheduleSection.hidden = false;

    // Afficher les métriques
    displayMetrics();

    // Générer les onglets de dates
    generateDateTabs();

    // Afficher le planning pour la première date
    currentDate = 0;
    renderScheduleTable();
}

function displayMetrics() {
    const defenses = planningData.Defense;
    const totalDefenses = defenses.length;

    // Compter les soutenances par jour
    const defensesPerDay = {};
    defenses.forEach(d => {
        if (!defensesPerDay[d.date]) {
            defensesPerDay[d.date] = 0;
        }
        defensesPerDay[d.date]++;
    });

    const daysCount = Object.keys(defensesPerDay).length;
    const avgDefenses = daysCount > 0 ? totalDefenses / daysCount : 0;
    const maxDefenses = Math.max(...Object.values(defensesPerDay));
    const minDefenses = Math.min(...Object.values(defensesPerDay));

    // Compter les salles utilisées
    const rooms = new Set(defenses.map(d => d.room_id));

    totalDefensesEl.textContent = totalDefenses;
    avgDefensesEl.textContent = avgDefenses.toFixed(1);
    maxDefensesEl.textContent = daysCount;
    minDefensesEl.textContent = rooms.size;
}

function generateDateTabs() {
    // Trouver toutes les dates uniques
    const dates = [...new Set(planningData.Defense.map(d => d.date))].sort((a, b) => a - b);

    dateTabs.innerHTML = '';

    dates.forEach((date, index) => {
        const tab = document.createElement('button');
        tab.className = `tab${index === 0 ? ' active' : ''}`;
        tab.textContent = `Jour ${date + 1}`;
        tab.dataset.date = date;
        tab.addEventListener('click', () => {
            selectDate(date, tab);
        });
        dateTabs.appendChild(tab);
    });
}

function selectDate(date, tabElement) {
    currentDate = date;

    // Mettre à jour les onglets actifs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });
    tabElement.classList.add('active');

    // Rendre le tableau
    renderScheduleTable();
}

function renderScheduleTable() {
    const defenses = planningData.Defense.filter(d => d.date === currentDate);

    if (defenses.length === 0) {
        scheduleContainer.innerHTML = `
            <div class="empty-state">
                <p>Aucune soutenance programmée pour ce jour.</p>
            </div>
        `;
        return;
    }

    // Récupérer toutes les salles utilisées ce jour
    const roomIds = [...new Set(defenses.map(d => d.room_id))].sort((a, b) => parseInt(a) - parseInt(b));

    // Récupérer tous les créneaux utilisés ce jour
    const usedSlots = [...new Set(defenses.map(d => d.schedule))].sort((a, b) => a - b);

    // Créer un dictionnaire pour accès rapide: schedule -> room_id -> defense
    const defenseMap = {};
    defenses.forEach(defense => {
        const key = `${defense.schedule}-${defense.room_id}`;
        defenseMap[key] = defense;
    });

    // Générer le HTML du tableau
    let html = `
        <div class="schedule-table-wrapper">
            <table class="schedule-table">
                <thead>
                    <tr>
                        <th>Créneau</th>
    `;

    // En-têtes des colonnes (salles)
    roomIds.forEach(roomId => {
        const roomName = getRoomName(roomId);
        html += `
            <th>
                <div class="room-header-content">
                    <div class="room-icon">
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                            <polyline points="9 22 9 12 15 12 15 22"></polyline>
                        </svg>
                    </div>
                    <span class="room-name">${roomName}</span>
                </div>
            </th>
        `;
    });

    html += `
                    </tr>
                </thead>
                <tbody>
    `;

    // Lignes du tableau (créneaux horaires)
    usedSlots.forEach(slotIndex => {
        const timeSlot = getTimeSlot(slotIndex);

        html += `
            <tr>
                <td class="time-slot-cell">
                    <div class="time-slot-content">
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"></circle>
                            <polyline points="12 6 12 12 16 14"></polyline>
                        </svg>
                        <span class="time-slot-text">${timeSlot}</span>
                    </div>
                </td>
        `;

        // Cellules pour chaque salle
        roomIds.forEach(roomId => {
            const key = `${slotIndex}-${roomId}`;
            const defense = defenseMap[key];

            if (defense) {
                const studentName = getStudentName(defense.student_id);
                const presidentName = getTeacherName(defense.defenseJury.president_id);
                const examinerName = getTeacherName(defense.defenseJury.examiner_id);
                const supervisorName = getTeacherName(defense.defenseJury.supervisor_id);

                html += `
                    <td>
                        <div class="defense-cell">
                            <div class="student-info">
                                <div class="student-label">Étudiant</div>
                                <div class="student-name">${studentName}</div>
                            </div>
                            <div class="jury-info">
                                <div class="jury-member president">
                                    <span class="jury-role">Président</span>
                                    <span class="jury-name">${presidentName}</span>
                                </div>
                                <div class="jury-member examiner">
                                    <span class="jury-role">Examinateur</span>
                                    <span class="jury-name">${examinerName}</span>
                                </div>
                                <div class="jury-member supervisor">
                                    <span class="jury-role">Encadrant</span>
                                    <span class="jury-name">${supervisorName}</span>
                                </div>
                            </div>
                        </div>
                    </td>
                `;
            } else {
                html += `
                    <td>
                        <div class="empty-cell">
                            <span>-</span>
                        </div>
                    </td>
                `;
            }
        });

        html += `</tr>`;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    scheduleContainer.innerHTML = html;
}

function getTimeSlot(scheduleIndex) {
    return timeSlots[scheduleIndex] || `Créneau ${scheduleIndex + 1}`;
}

function getRoomName(roomId) {
    return `Salle ${parseInt(roomId) + 1}`;
}

function getStudentName(studentId) {
    return `Étudiant ${studentId}`;
}

function getTeacherName(teacherId) {
    return `Enseignant ${teacherId}`;
}

function resetToUpload() {
    planningData = null;
    currentDate = 0;
    fileInput.value = '';

    // Afficher la section upload
    uploadSection.hidden = false;
    uploadSection.classList.remove('hidden');

    // Cacher la section planning
    scheduleSection.classList.add('hidden');
    scheduleSection.hidden = true;

    // Réinitialiser les métriques
    totalDefensesEl.textContent = '0';
    avgDefensesEl.textContent = '0';
    maxDefensesEl.textContent = '0';
    minDefensesEl.textContent = '0';

    // Vider les conteneurs
    dateTabs.innerHTML = '';
    scheduleContainer.innerHTML = '';
}



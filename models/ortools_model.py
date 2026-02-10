from ortools.sat.python import cp_model
import json
import uuid
import math
import logging
from datetime import datetime

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'ortools_scheduling_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Chargement des données JSON
logger.info("Chargement des données depuis simu.json...")
with open("simu.json", "r") as f:
    data = json.load(f)
logger.info("Données chargées avec succès")


def cp_ortools(data):
    logger.info("Début de la création du modèle OR-Tools CP-SAT")

    # ------------------------- Définition des classes -------------------------
    class Etudiant:
        def __init__(self, etdID: str, speciality: str, maitre_memoire_id: str, diplome: str):
            self.id = etdID
            self.speciality = speciality
            self.mm_id = maitre_memoire_id
            self.diplome = diplome
            self.a_soutenu = False

    class Enseignant:
        def __init__(self, ensgnID: str, specialities: list, grade: str, disponibilite: list[list]):
            self.id = ensgnID
            self.specialities = specialities
            self.grade = grade
            self.disponibilite = disponibilite
            self.nbre_soutenances = 0

    class Salle:
        def __init__(self, salleID: str, disponibilite: list[list]):
            self.id = salleID
            self.disponibilite = disponibilite
            self.occupee = False  # Verrouillage de la salle pendant un créneau

    # Rôles dans le jury: 0: Président, 1: Maître mémoire, 2: Examinateur

    # Correspondance des grades
    rank_values = {'Ingénieur': 1, 'Docteur': 2, 'MA': 3, 'MC': 4, 'Professeur': 5}
    g_min = 2  # Grade minimum requis pour être président

    # Initialisation des objets
    etudiants = [Etudiant(e["id"], e["speciality"], e["mm_id"], e["diplome"]) for e in data["students"]]
    enseignants = [Enseignant(e["id"], e["specialities"], rank_values[e["grade"]], e["disponibilite"]) for e in data["professeurs"]]
    salles = [Salle(s["id"], s["disponibilite"]) for s in data["salles"]]

    logger.info(f"Données chargées: {len(etudiants)} étudiants, {len(enseignants)} enseignants, {len(salles)} salles")
    logger.info(f"Jours de soutenance: 5, Créneaux horaires par jour: 8")

    # Création du modèle
    model = cp_model.CpModel()
    logger.info("Modèle CP-SAT créé")

    # Définition des ensembles
    jours = range(5)   # Jours de soutenance
    heures = range(8)  # Créneaux horaires par jour

    num_etudiants = len(etudiants)
    num_enseignants = len(enseignants)
    num_salles = len(salles)

    logger.info("Création des variables de décision...")

    # ------------------------- Variables de décision -------------------------
    # x[j, h, k, t] = 1 si l'étudiant t soutient le jour j à l'heure h dans la salle k
    x = {}
    for j in jours:
        for h in heures:
            for k in range(num_salles):
                for t in range(num_etudiants):
                    x[j, h, k, t] = model.NewBoolVar(f"x_{j}_{h}_{k}_{t}")

    # y[j, h, k, e, f] = 1 si l'enseignant e occupe le rôle f dans la soutenance jour j, heure h, salle k
    y = {}
    for j in jours:
        for h in heures:
            for k in range(num_salles):
                for e in range(num_enseignants):
                    for f in range(3):
                        y[j, h, k, e, f] = model.NewBoolVar(f"y_{j}_{h}_{k}_{e}_{f}")

    logger.info(f"Variables x créées: {len(x)} (affectation étudiants)")
    logger.info(f"Variables y créées: {len(y)} (affectation jury)")

    # g_max[j, h, k] : grade maximum du jury pour la soutenance (j, h, k)
    max_grade = max(ens.grade for ens in enseignants)
    g_max = {}
    for j in jours:
        for h in heures:
            for k in range(num_salles):
                g_max[j, h, k] = model.NewIntVar(0, max_grade, f"g_max_{j}_{h}_{k}")

    # ------------------------- Variables pour limiter les déplacements entre salles -------------------------
    # z[e, j, k] = 1 si l'enseignant e intervient dans la salle k le jour j
    z = {}
    for e in range(num_enseignants):
        for j in jours:
            for k in range(num_salles):
                z[e, j, k] = model.NewBoolVar(f"z_{e}_{j}_{k}")

    # w[e, j] mesure le nombre de salles en excès (au-delà d'une seule) utilisées par l'enseignant e le jour j
    w = {}
    for e in range(num_enseignants):
        for j in jours:
            w[e, j] = model.NewIntVar(0, num_salles, f"w_{e}_{j}")

    # Lien entre les affectations de jury et la salle utilisée :
    for e in range(num_enseignants):
        for j in jours:
            for k in range(num_salles):
                for h in heures:
                    for f in range(3):
                        # y[j, h, k, e, f] <= z[e, j, k]
                        model.AddImplication(y[j, h, k, e, f], z[e, j, k])

    # Contrainte pour pénaliser le changement de salle :
    for e in range(num_enseignants):
        for j in jours:
            # sum(z[e, j, k] for k) - 1 <= w[e, j]
            model.Add(sum(z[e, j, k] for k in range(num_salles)) - 1 <= w[e, j])

    # ------------------------- Fonctions de compatibilité -------------------------
    def MM(t, e):
        """Renvoie 1 si l'enseignant e est le maître de mémoire attitré de l'étudiant t."""
        return 1 if etudiants[t].mm_id == enseignants[e].id else 0

    def M_func(t, e):
        """Renvoie 1 si l'enseignant e est spécialiste dans la spécialité de l'étudiant t."""
        return 1 if etudiants[t].speciality in enseignants[e].specialities else 0

    logger.info("Ajout des contraintes dures...")

    # ------------------------- Contraintes Dures -------------------------

    # a) Chaque étudiant soutient une seule fois (au plus)
    for t in range(num_etudiants):
        model.Add(sum(x[j, h, k, t] for j in jours for h in heures for k in range(num_salles)) <= 1)
    logger.info("  ✓ Contrainte (a): Unicité de la soutenance par étudiant")

    # b) Pas de conflit horaire dans une salle (une seule soutenance par salle à un instant donné)
    for j in jours:
        for h in heures:
            for k in range(num_salles):
                model.Add(sum(x[j, h, k, t] for t in range(num_etudiants)) <= 1)
    logger.info("  ✓ Contrainte (b): Pas de conflit horaire dans les salles")

    # c) Pas de conflit horaire pour les enseignants (un enseignant ne peut être dans deux jurys en même temps)
    for e in range(num_enseignants):
        for j in jours:
            for h in heures:
                model.Add(sum(y[j, h, k, e, f] for k in range(num_salles) for f in range(3)) <= 1)
    logger.info("  ✓ Contrainte (c): Pas de conflit horaire pour les enseignants")

    # d) Disponibilité des enseignants
    for e in range(num_enseignants):
        for j in jours:
            for h in heures:
                for k in range(num_salles):
                    for f in range(3):
                        if enseignants[e].disponibilite[j][h] == 0:
                            model.Add(y[j, h, k, e, f] == 0)
    logger.info("  ✓ Contrainte (d): Disponibilité des enseignants")

    # e) Constitution du jury (exactement 3 membres par soutenance)
    for j in jours:
        for h in heures:
            for k in range(num_salles):
                # Nombre total de membres du jury = 3 * nombre de soutenances
                model.Add(
                    sum(y[j, h, k, e, f] for e in range(num_enseignants) for f in range(3))
                    == 3 * sum(x[j, h, k, t] for t in range(num_etudiants))
                )
                # Un enseignant ne peut avoir qu'un seul rôle dans une même soutenance
                for e in range(num_enseignants):
                    model.Add(sum(y[j, h, k, e, f] for f in range(3)) <= 1)

                # Au plus un seul président
                model.Add(sum(y[j, h, k, e, 0] for e in range(num_enseignants)) <= 1)

                # Le maître de mémoire doit être assigné
                model.Add(
                    sum(MM(t, e) * y[j, h, k, e, 1] for e in range(num_enseignants) for t in range(num_etudiants))
                    >= sum(x[j, h, k, t] for t in range(num_etudiants))
                )

                # L'examinateur doit être spécialiste
                model.Add(
                    sum(M_func(t, e) * y[j, h, k, e, 2] for e in range(num_enseignants) for t in range(num_etudiants))
                    >= sum(x[j, h, k, t] for t in range(num_etudiants))
                )
    logger.info("  ✓ Contrainte (e): Constitution du jury (3 membres)")

    # f) Contraintes sur le président du jury : grade minimum et sélection
    for j in jours:
        for h in heures:
            for k in range(num_salles):
                # Le président doit avoir un grade >= g_min
                model.Add(
                    sum(enseignants[e].grade * y[j, h, k, e, 0] for e in range(num_enseignants))
                    >= g_min * sum(x[j, h, k, t] for t in range(num_etudiants))
                )
                # Exactement un président si soutenance
                model.Add(
                    sum(y[j, h, k, e, 0] for e in range(num_enseignants))
                    == sum(x[j, h, k, t] for t in range(num_etudiants))
                )
    logger.info("  ✓ Contrainte (f): Président du jury (grade minimum)")

    # g) Limitation du nombre de soutenances par enseignant par jour (ici 4 par défaut)
    for e in range(num_enseignants):
        for j in jours:
            model.Add(
                sum(y[j, h, k, e, f] for h in heures for k in range(num_salles) for f in range(3))
                <= 4
            )
    logger.info("  ✓ Contrainte (g): Limitation à 4 soutenances par enseignant par jour")

    # h) Le président doit être le plus haut gradé du jury
    for j in jours:
        for h in heures:
            for k in range(num_salles):
                for e in range(num_enseignants):
                    for f in range(3):
                        # g_max[j, h, k] >= grade * y[j, h, k, e, f]
                        model.Add(g_max[j, h, k] >= enseignants[e].grade * y[j, h, k, e, f])
                # Le président a le grade max
                model.Add(
                    sum(enseignants[e].grade * y[j, h, k, e, 0] for e in range(num_enseignants))
                    == g_max[j, h, k]
                )
    logger.info("  ✓ Contrainte (h): Président = membre le plus haut gradé")

    # i) L'examinateur doit être spécialiste du domaine de l'étudiant
    for j in jours:
        for h in heures:
            for k in range(num_salles):
                for e in range(num_enseignants):
                    model.Add(
                        sum(M_func(t, e) * x[j, h, k, t] for t in range(num_etudiants))
                        >= y[j, h, k, e, 2]
                    )
                for t in range(num_etudiants):
                    for e in range(num_enseignants):
                        if not M_func(t, e):
                            # Si l'enseignant n'est pas spécialiste, il ne peut pas être examinateur pour cet étudiant
                            # y[j, h, k, e, 2] + x[j, h, k, t] <= 1 (linearization of y * x == 0)
                            model.Add(y[j, h, k, e, 2] + x[j, h, k, t] <= 1)
                    # Il doit y avoir au moins un examinateur pour chaque étudiant
                    model.Add(
                        x[j, h, k, t] <= sum(y[j, h, k, e, 2] for e in range(num_enseignants))
                    )

    # j) Le maître de mémoire de l'étudiant doit être présent (ou remplacé)
    for j in jours:
        for h in heures:
            for k in range(num_salles):
                for t in range(num_etudiants):
                    # Le MM attitré ou un autre enseignant doit être affecté comme MM
                    model.Add(
                        sum(MM(t, e) * y[j, h, k, e, 1] for e in range(num_enseignants))
                        + sum(y[j, h, k, e, 1] for e in range(num_enseignants) if not MM(t, e))
                        >= x[j, h, k, t]
                    )

    # ------------------------- Contraintes Soft -------------------------
    # Soft constraint 1 : Maximum de huit soutenances par jour dans une même salle
    p1 = 100  # Coefficient de pénalité pour la contrainte soft
    s = {}
    for j in jours:
        for k in range(num_salles):
            s[j, k] = model.NewIntVar(0, num_etudiants, f"s_soft_{j}_{k}")

    for j in jours:
        for k in range(num_salles):
            model.Add(
                sum(x[j, h, k, t] for h in heures for t in range(num_etudiants))
                <= 8 + s[j, k]
            )

    # ------------------------- Variables pour modéliser l'activité horaire des enseignants -------------------------
    # a[e, j, h] = 1 si l'enseignant e intervient le jour j à l'heure h
    a = {}
    for e in range(num_enseignants):
        for j in jours:
            for h in heures:
                a[e, j, h] = model.NewBoolVar(f"a_{e}_{j}_{h}")

    # Lien entre a et y : pour chaque enseignant e, jour j, heure h
    for e in range(num_enseignants):
        for j in jours:
            for h in heures:
                # a[e, j, h] = 1 ssi au moins un y[j, h, k, e, f] == 1
                # a[e, j, h] >= y[j, h, k, e, f] pour tout k, f
                # a[e, j, h] <= sum(y[j, h, k, e, f] for k, f)
                all_y = [y[j, h, k, e, f] for k in range(num_salles) for f in range(3)]
                model.AddMaxEquality(a[e, j, h], all_y + [model.NewConstant(0)])  # a = max(all_y)

    # Variables pour définir la plage d'activité horaire d'un enseignant le même jour
    # T_min[e, j] : première heure d'intervention
    # T_max[e, j] : dernière heure d'intervention
    T_min = {}
    T_max = {}
    big_M = len(heures)

    for e in range(num_enseignants):
        for j in jours:
            T_min[e, j] = model.NewIntVar(0, len(heures) - 1, f"T_min_{e}_{j}")
            T_max[e, j] = model.NewIntVar(0, len(heures) - 1, f"T_max_{e}_{j}")

    for e in range(num_enseignants):
        for j in jours:
            for h in heures:
                # T_min[e, j] <= h + (1 - a[e, j, h]) * big_M
                # If a[e,j,h] == 1 => T_min[e,j] <= h
                model.Add(T_min[e, j] <= h).OnlyEnforceIf(a[e, j, h])
                # T_max[e, j] >= h - (1 - a[e, j, h]) * big_M
                # If a[e,j,h] == 1 => T_max[e,j] >= h
                model.Add(T_max[e, j] >= h).OnlyEnforceIf(a[e, j, h])

    # Variable pour le temps d'attente (wasted time) : différence entre la durée totale de présence et le nombre de créneaux actifs
    waiting_time = {}
    for e in range(num_enseignants):
        for j in jours:
            waiting_time[e, j] = model.NewIntVar(0, len(heures), f"waiting_time_{e}_{j}")

    for e in range(num_enseignants):
        for j in jours:
            model.Add(
                waiting_time[e, j] >= T_max[e, j] - T_min[e, j] + 1 - sum(a[e, j, h] for h in heures)
            )

    # ------------------------- Fonction Objective -------------------------
    # Coefficient p2 pour le changement de salle et p3 pour le temps d'attente
    p2 = 10  # Pénalité pour changement de salle
    p3 = 5   # Pénalité pour temps d'attente

    objective_terms = []

    # Maximiser le nombre de soutenances
    for j in jours:
        for h in heures:
            for k in range(num_salles):
                for t in range(num_etudiants):
                    objective_terms.append(x[j, h, k, t])

    # Pénalité pour dépassement de 8 soutenances par jour par salle
    for j in jours:
        for k in range(num_salles):
            objective_terms.append(-p1 * s[j, k])

    # Pénalité pour changement de salle
    for e in range(num_enseignants):
        for j in jours:
            objective_terms.append(-p2 * w[e, j])

    # Pénalité pour temps d'attente
    for e in range(num_enseignants):
        for j in jours:
            objective_terms.append(-p3 * waiting_time[e, j])

    model.Maximize(sum(objective_terms))

    # ------------------------- Résolution -------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 300.0  # Limite de temps de 5 minutes
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL:
        print("Une solution optimale a été trouvée.")
    elif status == cp_model.FEASIBLE:
        print("Une solution réalisable a été trouvée (pas nécessairement optimale).")
    elif status == cp_model.INFEASIBLE:
        print("Le modèle est infaisable. Vérifiez les contraintes.")
        return None
    elif status == cp_model.MODEL_INVALID:
        print("Le modèle est invalide.")
        return None
    else:
        print("Le solveur n'a pas trouvé de solution.")
        return None

    # ------------------------- Affichage simple -------------------------------------------
    print("🔍 Vérification des soutenances planifiées...\n")
    nb_soutenances = sum(
        solver.Value(x[j, h, k, t])
        for j in jours
        for h in heures
        for k in range(num_salles)
        for t in range(num_etudiants)
    )
    print(f"📊 Nombre total de soutenances programmées : {int(nb_soutenances)}")

    # ------------------------- Construction du dictionnaire de planification --------------------------------
    planning = {}
    defense_list = []

    # Construire la liste des défenses
    for j in jours:
        for h in heures:
            for k in range(num_salles):
                for t in range(num_etudiants):
                    if solver.Value(x[j, h, k, t]) > 0.5:
                        defense_id = str(uuid.uuid4())
                        student_id = etudiants[t].id
                        room_id = salles[k].id
                        schedule = h  # ici, on considère h comme l'indice du créneau horaire
                        date = j      # ici, j représente le jour, à adapter selon vos besoins

                        # Construire le dictionnaire pour le jury avec les rôles attendus
                        jury_info = {
                            "president_id": None,
                            "examiner_id": None,
                            "supervisor_id": None
                        }
                        for e in range(num_enseignants):
                            for f in range(3):
                                if solver.Value(y[j, h, k, e, f]) > 0.5:
                                    if f == 0:  # Président
                                        jury_info["president_id"] = enseignants[e].id
                                    elif f == 1:  # Maître de mémoire → supervisor_id
                                        jury_info["supervisor_id"] = enseignants[e].id
                                    elif f == 2:  # Examinateur
                                        jury_info["examiner_id"] = enseignants[e].id

                        defense = {
                            "student_id": student_id,
                            "defenseJury": jury_info,
                            "room_id": room_id,
                            "schedule": schedule,
                            "date": date
                        }
                        defense_list.append(defense)

    planning["Defense"] = defense_list

    # Calcul des métriques sur le nombre de soutenances par professeur
    prof_defenses = []
    for e in range(num_enseignants):
        # Pour chaque enseignant, on compte le nombre de fois où il est affecté à un rôle dans le planning
        count = sum(
            solver.Value(y[j, h, k, e, f])
            for j in jours
            for h in heures
            for k in range(num_salles)
            for f in range(3)
        )
        prof_defenses.append(count)

    total_soutenances = nb_soutenances
    if prof_defenses:
        moyenne_soutenances = sum(prof_defenses) / len(prof_defenses)
        max_defenses = max(prof_defenses)
        min_defenses = min(prof_defenses)
        stdev_defenses = math.sqrt(sum((val - moyenne_soutenances) ** 2 for val in prof_defenses) / len(prof_defenses))
    else:
        moyenne_soutenances = 0
        max_defenses = 0
        min_defenses = 0
        stdev_defenses = 0

    planning["metriques"] = {
        "total_soutenances": int(total_soutenances),
        "moyenne_soutenances": moyenne_soutenances,
        "max_defenses": max_defenses,
        "min_defenses": min_defenses,
        "stdev_defenses": stdev_defenses
    }

    logger.info("Métriques calculées:")
    logger.info(f"  - Total soutenances: {int(total_soutenances)}")
    logger.info(f"  - Moyenne par prof: {moyenne_soutenances:.2f}")
    logger.info(f"  - Max participations: {max_defenses}")
    logger.info(f"  - Min participations: {min_defenses}")
    logger.info(f"  - Écart-type: {stdev_defenses:.2f}")
    logger.info("Planification terminée avec succès!")

    return planning


# Exécution
if __name__ == "__main__":
    result = cp_ortools(data=data)
    # Sauvegarde du résultat dans un fichier JSON
    with open("planning_ortools.json", "w") as f:
        json.dump(result, f, indent=4)


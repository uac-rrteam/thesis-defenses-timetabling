import gurobipy as gp
from gurobipy import GRB, quicksum
import json
import uuid
import math

# Chargement des données JSON
with open("pre_soutenance_L.json", "r") as f:
    data = json.load(f)

def cp (data):

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


    # Rôles dans le jury: 0: Président, 1: Maître mémoire, 2: Examinateur

    # Correspondance des grades
    rank_values = {'Ing.': 1, 'Dr': 2, 'MA': 3, 'MC': 4, 'Prof.': 5}
    g_min = 2  # Grade minimum requis pour être président

    # Initialisation des objets
    etudiants = [Etudiant(e["id"], e["speciality"], e.get("mm_id"), e["diplome"]) for e in data["students"]]
    enseignants = [Enseignant(e["id"], e["specialities"], rank_values[e["grade"]], e["disponibilite"]) for e in data["professeurs"]]


    # Création du modèle
    model = gp.Model("Soutenances")

    # Définition des ensembles
    jours = range(2)   # Jours de soutenance
    heures = range(8)  # Créneaux horaires par jour
    parallel_sessions = range(7)  # 7 soutenances en parallèle nécessaires pour 106 étudiants

    # ------------------------- Variables de décision -------------------------
    x = model.addVars(jours, heures, parallel_sessions, range(len(etudiants)), vtype=GRB.BINARY, name="x")
    y = model.addVars(jours, heures, parallel_sessions, range(len(enseignants)), range(3), vtype=GRB.BINARY, name="y")
    g_max = model.addVars(jours, heures, parallel_sessions, vtype=GRB.INTEGER, name="g_max")

    # Association de la variable x au callback
    model._x = x

    # ------------------------- Fonctions de compatibilité -------------------------

    def M(t, e):
        """Renvoie 1 si l'enseignant e est spécialiste dans la spécialité de l'étudiant t."""
        return 1 if etudiants[t].speciality in enseignants[e].specialities else 0

    # ------------------------- Contraintes Dures -------------------------

    # a) Chaque étudiant soutient une seule fois (toutes sessions parallèles confondues)
    for t in range(len(etudiants)):
        model.addConstr(
            quicksum(x[j, h, p, t] for j in jours for h in heures for p in parallel_sessions) <= 1,
            name=f"Unique_Soutenance_Etudiant_{t}"
        )

    # c) Pas de conflit horaire pour les enseignants (un enseignant ne peut être dans deux jurys en même temps)
    for e in range(len(enseignants)):
        for j in jours:
            for h in heures:
                model.addConstr(
                    quicksum(y[j, h, p, e, f] for p in parallel_sessions for f in range(3)) <= 1,
                    name=f"Conflit_Horaire_Enseignant_{e}{j}{h}"
                )

    # d) Disponibilité des enseignants
    for e in range(len(enseignants)):
        for j in jours:
            for h in heures:
                for p in parallel_sessions:
                    for f in range(3):
                        model.addConstr(
                            y[j, h, p, e, f] <= enseignants[e].disponibilite[j][h],
                            name=f"Disponibilite_Enseignant_{e}{j}{h}{p}{f}"
                        )

    # e) Constitution du jury (2 membres par soutenance)
    for j in jours:
        for h in heures:
            for p in parallel_sessions:
                model.addConstr(
                    gp.quicksum(y[j, h, p, e, f] for e in range(len(enseignants)) for f in range(3))
                    == 2 * gp.quicksum(x[j, h, p, t] for t in range(len(etudiants))),
                    name=f"Taille_Jury_{j}{h}{p}"
                )
                model.addConstr(
                    gp.quicksum(y[j, h, p, e, f] for e in range(len(enseignants)) for f in range(3))
                    <= 3 * gp.quicksum(x[j, h, p, t] for t in range(len(etudiants))),
                    name=f"Taille_Jury_Max_{j}{h}{p}"
                )
                for e in range(len(enseignants)):
                    model.addConstr(
                        gp.quicksum(y[j, h, p, e, f] for f in range(3)) <= 1,
                        name=f"Unique_Role_Enseignant_{e}{j}{h}{p}"
                    )
                model.addConstr(
                    gp.quicksum(y[j, h, p, e, 0] for e in range(len(enseignants)))
                    <= 1,
                    name=f"Un_Seul_President_{j}{h}{p}"
                )
                model.addConstr(
                    gp.quicksum(M(t, e) * y[j, h, p, e, 2] for e in range(len(enseignants)) for t in range(len(etudiants)))
                    >= gp.quicksum(x[j, h, p, t] for t in range(len(etudiants))),
                    name=f"Examinateur_Assigne_{j}{h}{p}"
                )

    # f) Contraintes sur le président du jury : grade minimum et sélection
    for j in jours:
        for h in heures:
            for p in parallel_sessions:
                model.addConstr(
                    gp.quicksum(enseignants[e].grade * y[j, h, p, e, 0] for e in range(len(enseignants)))
                    >= g_min * gp.quicksum(x[j, h, p, t] for t in range(len(etudiants))),
                    name=f"President_Grade_Min_{j}{h}{p}"
                )
                model.addConstr(
                    gp.quicksum(y[j, h, p, e, 0] for e in range(len(enseignants)))
                    == gp.quicksum(x[j, h, p, t] for t in range(len(etudiants))),
                    name=f"President_Obligatoire_{j}{h}{p}"
                )

    # g) Limitation du nombre de soutenances par enseignant par jour (augmenté pour le format en ligne)
    for e in range(len(enseignants)):
        for j in jours:
            model.addConstr(
                quicksum(y[j, h, p, e, f] for h in heures for p in parallel_sessions for f in range(3))
                <= 8,  # Un enseignant peut participer à toutes les soutenances d'un jour
                name=f"Limite_Soutenances_Enseignant_{e}_{j}"
            )

    # h) Le président doit être le plus haut gradé du jury
    for j in jours:
        for h in heures:
            for p in parallel_sessions:
                for e in range(len(enseignants)):
                    for f in range(3):
                        model.addConstr(
                            g_max[j, h, p] >= enseignants[e].grade * y[j, h, p, e, f],
                            name=f"Max_Grade_{j}{h}{p}{e}{f}"
                        )
                model.addConstr(
                    gp.quicksum(enseignants[e].grade * y[j, h, p, e, 0] for e in range(len(enseignants)))
                    == g_max[j, h, p],
                    name=f"President_Grade_Max_{j}{h}{p}"
                )

    # i) L'examinateur doit être spécialiste du domaine de l'étudiant
    for j in jours:
        for h in heures:
            for p in parallel_sessions:
                for e in range(len(enseignants)):
                    model.addConstr(
                        gp.quicksum(M(t, e) * x[j, h, p, t] for t in range(len(etudiants)))
                        >= y[j, h, p, e, 2],
                        name=f"Specialite_Examinateur_{j}{h}{p}_{e}"
                    )
                for t in range(len(etudiants)):
                    for e in range(len(enseignants)):
                        if not M(t, e):
                            model.addConstr(
                                y[j, h, p, e, 2] * x[j, h, p, t] == 0,
                                name=f"Interdiction_Examinateur_{j}{h}{p}{t}{e}"
                            )
                    model.addConstr(
                        x[j, h, p, t] <= gp.quicksum(y[j, h, p, e, 2] for e in range(len(enseignants))),
                        name=f"Existence_Examinateur_{j}{h}{p}_{t}"
                    )

    # ------------------------- Variables pour modéliser l'activité horaire des enseignants -------------------------
    # a[e,j,h] = 1 si l'enseignant e intervient le jour j à l'heure h
    a = model.addVars(range(len(enseignants)), jours, heures, vtype=GRB.BINARY, name="a")

    # Lien entre a et y : pour chaque enseignant e, jour j, heure h
    for e in range(len(enseignants)):
        for j in jours:
            for h in heures:
                model.addConstr(
                    a[e, j, h] == gp.quicksum(y[j, h, p, e, f] for p in parallel_sessions for f in range(3)),
                    name=f"Link_a_y_{e}{j}{h}"
                )

    # Variables pour définir la plage d'activité horaire d'un enseignant le même jour
    # T_min[e,j] : première heure d'intervention
    # T_max[e,j] : dernière heure d'intervention
    T_min = model.addVars(range(len(enseignants)), jours, vtype=GRB.CONTINUOUS, lb=0, ub=len(heures)-1, name="T_min")
    T_max = model.addVars(range(len(enseignants)), jours, vtype=GRB.CONTINUOUS, lb=0, ub=len(heures)-1, name="T_max")
    M = len(heures)  # Big-M

    for e in range(len(enseignants)):
        for j in jours:
            for h in heures:
                model.addConstr(
                    T_min[e, j] <= h + (1 - a[e, j, h]) * M,
                    name=f"Tmin_constraint_{e}{j}{h}"
                )
                model.addConstr(
                    T_max[e, j] >= h - (1 - a[e, j, h]) * M,
                    name=f"Tmax_constraint_{e}{j}{h}"
                )

    # Variable pour le temps d'attente (wasted time) : différence entre la durée totale de présence et le nombre de créneaux actifs
    waiting_time = model.addVars(range(len(enseignants)), jours, vtype=GRB.CONTINUOUS, lb=0, name="waiting_time")

    for e in range(len(enseignants)):
        for j in jours:
            model.addConstr(
                waiting_time[e, j] >= T_max[e, j] - T_min[e, j] + 1 - gp.quicksum(a[e, j, h] for h in heures),
                name=f"waiting_time_{e}_{j}"
            )

    # ------------------------- Fonction Objective -------------------------
    p1 = 100  # Priorité pour planifier les soutenances
    p2 = 10   # Bonus pour les soutenances parallèles
    p3 = 1    # Pénalité pour temps d'attente

    model.setObjective(
        p1 * gp.quicksum(x[j, h, p, t] for j in jours for h in heures for p in parallel_sessions for t in range(len(etudiants)))
        + p2 * gp.quicksum(gp.quicksum(x[j, h, p, t] for t in range(len(etudiants)) for p in parallel_sessions) for j in jours for h in heures)
        - p3 * gp.quicksum(waiting_time[e, j] for e in range(len(enseignants)) for j in jours),
        GRB.MAXIMIZE
    )

    # ------------------------- Résolution -------------------------
    model.optimize()

    print("-"*18)

    if model.status == GRB.OPTIMAL:
        print("Une solution optimale a été trouvée.")
    elif model.status == GRB.INFEASIBLE:
        print("Le modèle est infaisable. Vérifiez les contraintes.")
        model.computeIIS()
        model.write("infeasible_model.ilp")
    elif model.status == GRB.UNBOUNDED:
        print("Le modèle est non borné.")
    else:
        print("Le solveur n'a pas trouvé de solution.")

    
    # ------------------------- Affichage simple -------------------------------------------
    print("🔍 Vérification des soutenances planifiées...\n")
    nb_soutenances = sum(x[j, h, p, t].X for j in jours for h in heures for p in parallel_sessions for t in range(len(etudiants)))
    print(f"📊 Nombre total de soutenances programmées : {int(nb_soutenances)}")
    
    # Affichage détaillé des soutenances
    for j in jours:
        for h in heures:
            soutenances_paralleles = 0
            for p in parallel_sessions:
                for t in range(len(etudiants)):
                    if x[j, h, p, t].X > 0.5:
                        soutenances_paralleles += 1
            if soutenances_paralleles > 0:
                print(f"\n� Jour {j+1}, Heure {h+1}: {soutenances_paralleles} soutenance(s) en parallèle")
 
    # ------------------------- Construction du dictionnaire de planification --------------------------------
    planning = {}
    defense_list = []
    
    # Calculer le nombre total de soutenances programmées (basé sur la variable x)
    nb_soutenances = sum(
        x[j, h, p, t].X 
        for j in jours 
        for h in heures 
        for p in parallel_sessions
        for t in range(len(etudiants))
    )
    
    # Construire la liste des défenses
    for j in jours:
        for h in heures:
            for p in parallel_sessions:
                for t in range(len(etudiants)):
                    if x[j, h, p, t].X > 0.5:
                        defense_id = str(uuid.uuid4())
                        student_id = etudiants[t].id
                        schedule = h  # ici, on considère h comme l'indice du créneau horaire
                        date = j      # ici, j représente le jour, à adapter selon vos besoins

                        # Construire le dictionnaire pour le jury avec les rôles attendus
                        jury_info = {
                            "president_id": None,
                            "examiner_id": None,
                        }
                        for e in range(len(enseignants)):
                            if y[j, h, p, e, 0].X > 0.5:  # Président
                                jury_info["president_id"] = enseignants[e].id
                            if y[j, h, p, e, 2].X > 0.5:  # Examinateur
                                jury_info["examiner_id"] = enseignants[e].id

                        defense = {
                            "student_id": student_id,
                            "defenseJury": jury_info,
                            "schedule": schedule,
                            "date": date
                        }
                        defense_list.append(defense)
    
    planning["Defense"] = defense_list

    # ------------------------- Calcul des métriques -------------------------
    """
    Les métriques calculées sont :
    1. Pour l'ensemble des soutenances :
       - total_soutenances : Nombre total de soutenances programmées
       - taux_occupation : Pourcentage d'utilisation des créneaux disponibles
       - etudiants_non_programmes : Nombre d'étudiants sans soutenance programmée
    
    2. Pour la répartition par jour :
       - soutenances_jour1 : Nombre de soutenances le premier jour
       - soutenances_jour2 : Nombre de soutenances le deuxième jour
    
    3. Pour la charge des enseignants :
       - moyenne_soutenances : Moyenne du nombre de participations par enseignant
       - max_defenses : Nombre maximum de participations pour un enseignant
       - min_defenses : Nombre minimum de participations pour un enseignant
       - stdev_defenses : Écart-type des participations (mesure de l'équité de la répartition)
       - max_president : Nombre maximum de fois qu'un enseignant est président
       - max_examiner : Nombre maximum de fois qu'un enseignant est examinateur
    """
    
    # Calcul des métriques sur le nombre de soutenances par professeur
    prof_defenses = []
    for e in range(len(enseignants)):
        # Pour chaque enseignant, on compte le nombre de fois où il est affecté à un rôle dans le planning
        count = sum(
            y[j, h, p, e, f].X 
            for j in jours 
            for h in heures
            for p in parallel_sessions
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

    # Calcul du nombre de présidences et d'examens par enseignant
    # Ces métriques permettent de vérifier la répartition des rôles
    president_counts = [sum(y[j, h, p, e, 0].X for j in jours for h in heures for p in parallel_sessions) for e in range(len(enseignants))]
    examiner_counts = [sum(y[j, h, p, e, 2].X for j in jours for h in heures for p in parallel_sessions) for e in range(len(enseignants))]
    
    # Calcul de la répartition des soutenances par jour
    # Ces métriques permettent de vérifier l'équilibre entre les deux jours
    soutenances_jour1 = sum(x[0, h, p, t].X for h in heures for p in parallel_sessions for t in range(len(etudiants)))
    soutenances_jour2 = sum(x[1, h, p, t].X for h in heures for p in parallel_sessions for t in range(len(etudiants)))
    
    # Vérification de la couverture des étudiants
    # Cette métrique permet de s'assurer que tous les étudiants sont programmés
    etudiants_non_programmes = len(etudiants) - int(total_soutenances)

    # Construction du dictionnaire des métriques avec leurs descriptions
    planning["metriques"] = {
        # Métriques générales
        "total_soutenances": {
            "valeur": int(total_soutenances),
            "description": "Nombre total de soutenances programmées"
        },
        "taux_occupation": {
            "valeur": (total_soutenances / (len(jours) * len(heures) * len(parallel_sessions))) * 100,
            "description": "Pourcentage d'utilisation des créneaux disponibles"
        },
        "etudiants_non_programmes": {
            "valeur": etudiants_non_programmes,
            "description": "Nombre d'étudiants qui n'ont pas encore de soutenance programmée"
        },
        
        # Métriques de répartition par jour
        "soutenances_jour1": {
            "valeur": int(soutenances_jour1),
            "description": "Nombre de soutenances programmées le premier jour"
        },
        "soutenances_jour2": {
            "valeur": int(soutenances_jour2),
            "description": "Nombre de soutenances programmées le deuxième jour"
        },
        
        # Métriques de charge des enseignants
        "moyenne_soutenances": {
            "valeur": moyenne_soutenances,
            "description": "Nombre moyen de participations aux jurys par enseignant"
        },
        "max_defenses": {
            "valeur": max_defenses,
            "description": "Nombre maximum de participations aux jurys pour un enseignant"
        },
        "min_defenses": {
            "valeur": min_defenses,
            "description": "Nombre minimum de participations aux jurys pour un enseignant"
        },
        "stdev_defenses": {
            "valeur": stdev_defenses,
            "description": "Écart-type du nombre de participations (mesure de l'équité de la répartition)"
        },
        "max_president": {
            "valeur": max(president_counts),
            "description": "Nombre maximum de fois qu'un enseignant est président"
        },
        "max_examiner": {
            "valeur": max(examiner_counts),
            "description": "Nombre maximum de fois qu'un enseignant est examinateur"
        }
    }
    
    # Sauvegarde du résultat dans un fichier JSON
    with open("resultat_planning.json", "w", encoding="utf-8") as f:
        json.dump(planning, f, ensure_ascii=False, indent=4)
    return planning

cp(data=data)


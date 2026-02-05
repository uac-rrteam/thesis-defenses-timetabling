import gurobipy as gp
from gurobipy import GRB, quicksum
import json
import uuid
import math

# Chargement des données JSON
with open("simu.json", "r") as f:
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

    # Création du modèle
    model = gp.Model("Soutenances")

    # Définition des ensembles
    jours = range(5)   # Jours de soutenance
    heures = range(8)  # Créneaux horaires par jour

    # ------------------------- Variables de décision -------------------------
    x = model.addVars(jours, heures, range(len(salles)), range(len(etudiants)), vtype=GRB.BINARY, name="x")
    y = model.addVars(jours, heures, range(len(salles)), range(len(enseignants)), range(3), vtype=GRB.BINARY, name="y")
    g_max = model.addVars(jours, heures, range(len(salles)), vtype=GRB.INTEGER, name="g_max")

    # Association de la variable x au callback
    model._x = x

    # ------------------------- Variables pour limiter les déplacements entre salles -------------------------
    # z[e,j,k] = 1 si l'enseignant e intervient dans la salle k le jour j
    z = model.addVars(range(len(enseignants)), jours, range(len(salles)), vtype=GRB.BINARY, name="z")
    # w[e,j] mesure le nombre de salles en excès (au-delà d'une seule) utilisées par l'enseignant e le jour j
    w = model.addVars(range(len(enseignants)), jours, vtype=GRB.CONTINUOUS, lb=0, name="w")

    # Lien entre les affectations de jury et la salle utilisée :
    for e in range(len(enseignants)):
        for j in jours:
            for k in range(len(salles)):
                for h in heures:
                    for f in range(3):
                        model.addConstr(
                            y[j, h, k, e, f] <= z[e, j, k],
                            name=f"Link_y_z_{e}{j}{k}{h}{f}"
                        )

    # Contrainte pour pénaliser le changement de salle :
    for e in range(len(enseignants)):
        for j in jours:
            model.addConstr(
                gp.quicksum(z[e, j, k] for k in range(len(salles))) - 1 <= w[e, j],
                name=f"RoomChange_{e}_{j}"
            )


    # ------------------------- Fonctions de compatibilité -------------------------
    def MM(t, e):
        """Renvoie 1 si l'enseignant e est le maître de mémoire attitré de l'étudiant t."""
        return 1 if etudiants[t].mm_id == enseignants[e].id else 0


    def M(t, e):
        """Renvoie 1 si l'enseignant e est spécialiste dans la spécialité de l'étudiant t."""
        return 1 if etudiants[t].speciality in enseignants[e].specialities else 0


    # ------------------------- Contraintes Dures -------------------------

    # a) Chaque étudiant soutient une seule fois
    for t in range(len(etudiants)):
        model.addConstr(
            quicksum(x[j, h, k, t] for j in jours for h in heures for k in range(len(salles))) <= 1,
            name=f"Unique_Soutenance_Etudiant_{t}"
        )

    # b) Pas de conflit horaire dans une salle (une seule soutenance par salle à un instant donné)
    for j in jours:
        for h in heures:
            for k in range(len(salles)):
                model.addConstr(
                    quicksum(x[j, h, k, t] for t in range(len(etudiants))) <= 1,
                    name=f"Conflit_Horaire_Salle_{j}{h}{k}"
                )

    # c) Pas de conflit horaire pour les enseignants (un enseignant ne peut être dans deux jurys en même temps)
    for e in range(len(enseignants)):
        for j in jours:
            for h in heures:
                model.addConstr(
                    quicksum(y[j, h, k, e, f] for k in range(len(salles)) for f in range(3)) <= 1,
                    name=f"Conflit_Horaire_Enseignant_{e}{j}{h}"
                )

    # d) Disponibilité des enseignants
    for e in range(len(enseignants)):
        for j in jours:
            for h in heures:
                for k in range(len(salles)):
                    for f in range(3):
                        model.addConstr(
                            y[j, h, k, e, f] <= enseignants[e].disponibilite[j][h],
                            name=f"Disponibilite_Enseignant_{e}{j}{h}{k}{f}"
                        )

    # e) Constitution du jury (exactement 3 membres par soutenance)
    for j in jours:
        for h in heures:
            for k in range(len(salles)):
                model.addConstr(
                    gp.quicksum(y[j, h, k, e, f] for e in range(len(enseignants)) for f in range(3))
                    == 3 * gp.quicksum(x[j, h, k, t] for t in range(len(etudiants))),
                    name=f"Taille_Jury_{j}{h}{k}"
                )
                for e in range(len(enseignants)):
                    model.addConstr(
                        gp.quicksum(y[j, h, k, e, f] for f in range(3)) <= 1,
                        name=f"Unique_Role_Enseignant_{e}{j}{h}_{k}"
                    )
                model.addConstr(
                    gp.quicksum(y[j, h, k, e, 0] for e in range(len(enseignants)))
                    <= 1,
                    name=f"Un_Seul_President_{j}{h}{k}"
                )
                model.addConstr(
                    gp.quicksum(MM(t, e) * y[j, h, k, e, 1] for e in range(len(enseignants)) for t in range(len(etudiants)))
                    >= gp.quicksum(x[j, h, k, t] for t in range(len(etudiants))),
                    name=f"Maitre_Memoire_Assigne_{j}{h}{k}"
                )
                model.addConstr(
                    gp.quicksum(M(t, e) * y[j, h, k, e, 2] for e in range(len(enseignants)) for t in range(len(etudiants)))
                    >= gp.quicksum(x[j, h, k, t] for t in range(len(etudiants))),
                    name=f"Examinateur_Assigne_{j}{h}{k}"
                )

    # f) Contraintes sur le président du jury : grade minimum et sélection
    for j in jours:
        for h in heures:
            for k in range(len(salles)):
                model.addConstr(
                    gp.quicksum(enseignants[e].grade * y[j, h, k, e, 0] for e in range(len(enseignants)))
                    >= g_min * gp.quicksum(x[j, h, k, t] for t in range(len(etudiants))),
                    name=f"President_Grade_Min_{j}{h}{k}"
                )
                model.addConstr(
                    gp.quicksum(y[j, h, k, e, 0] for e in range(len(enseignants)))
                    == gp.quicksum(x[j, h, k, t] for t in range(len(etudiants))),
                    name=f"President_Obligatoire_{j}{h}{k}"
                )

    # g) Limitation du nombre de soutenances par enseignant par jour (ici 4 par défaut)
    for e in range(len(enseignants)):
        for j in jours:
            model.addConstr(
                quicksum(y[j, h, k, e, f] for h in heures for k in range(len(salles)) for f in range(3))
                <= 4,
                name=f"Limite_Soutenances_Enseignant_{e}_{j}"
            )

    # h) Le président doit être le plus haut gradé du jury
    for j in jours:
        for h in heures:
            for k in range(len(salles)):
                for e in range(len(enseignants)):
                    for f in range(3):
                        model.addConstr(
                            g_max[j, h, k] >= enseignants[e].grade * y[j, h, k, e, f],
                            name=f"Max_Grade_{j}{h}{k}{e}{f}"
                        )
                model.addConstr(
                    gp.quicksum(enseignants[e].grade * y[j, h, k, e, 0] for e in range(len(enseignants)))
                    == g_max[j, h, k],
                    name=f"President_Grade_Max_{j}{h}{k}"
                )

    # i) L'examinateur doit être spécialiste du domaine de l'étudiant
    for j in jours:
        for h in heures:
            for k in range(len(salles)):
                for e in range(len(enseignants)):
                    model.addConstr(
                        gp.quicksum(M(t, e) * x[j, h, k, t] for t in range(len(etudiants)))
                        >= y[j, h, k, e, 2],
                        name=f"Specialite_Examinateur_{j}{h}{k}_{e}"
                    )
                for t in range(len(etudiants)):
                    for e in range(len(enseignants)):
                        if not M(t, e):
                            model.addConstr(
                                y[j, h, k, e, 2] * x[j, h, k, t] == 0,
                                name=f"Interdiction_Examinateur_{j}{h}{k}{t}{e}"
                            )
                    model.addConstr(
                        x[j, h, k, t] <= gp.quicksum(y[j, h, k, e, 2] for e in range(len(enseignants))),
                        name=f"Existence_Examinateur_{j}{h}{k}_{t}"
                    )

    # j) Le maître de mémoire de l'étudiant doit être présent (ou remplacé)
    for j in jours:
        for h in heures:
            for k in range(len(salles)):
                for t in range(len(etudiants)):
                    model.addConstr(
                        gp.quicksum(MM(t, e) * y[j, h, k, e, 1] for e in range(len(enseignants)))
                        + gp.quicksum(y[j, h, k, e, 1] for e in range(len(enseignants)) if not MM(t, e))
                        >= x[j, h, k, t],
                        name=f"Maitre_Memoire_Present_{j}{h}{k}_{t}"
                    )

    # ------------------------- Contraintes Soft -------------------------
    # Soft constraint 1 : Maximum de huit soutenances par jour dans une même salle
    p1 = 100  # Coefficient de pénalité pour la contrainte soft
    s = model.addVars(jours, range(len(salles)), vtype=GRB.CONTINUOUS, lb=0, name="s_soft")

    for j in jours:
        for k in range(len(salles)):
            model.addConstr(
                quicksum(x[j, h, k, t] for h in heures for t in range(len(etudiants)))
                <= 8 + s[j, k],
                name=f"Soft_Max8_Soutenances_{j}_{k}"
            )

    # ------------------------- Variables pour modéliser l'activité horaire des enseignants -------------------------
    # a[e,j,h] = 1 si l'enseignant e intervient le jour j à l'heure h
    a = model.addVars(range(len(enseignants)), jours, heures, vtype=GRB.BINARY, name="a")

    # Lien entre a et y : pour chaque enseignant e, jour j, heure h
    for e in range(len(enseignants)):
        for j in jours:
            for h in heures:
                model.addConstr(
                    a[e, j, h] == gp.quicksum(y[j, h, k, e, f] for k in range(len(salles)) for f in range(3)),
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
    # Coefficient p2 pour le changement de salle et p3 pour le temps d'attente
    p2 = 10  # Pénalité pour changement de salle
    p3 = 5   # Pénalité pour temps d'attente

    model.setObjective(
        gp.quicksum(x[j, h, k, t] for j in jours for h in heures for k in range(len(salles)) for t in range(len(etudiants)))
        - p1 * gp.quicksum(s[j, k] for j in jours for k in range(len(salles)))
        - p2 * gp.quicksum(w[e, j] for e in range(len(enseignants)) for j in jours)
        - p3 * gp.quicksum(waiting_time[e, j] for e in range(len(enseignants)) for j in jours),
        GRB.MAXIMIZE
    )

    # ------------------------- Résolution -------------------------
    model.optimize()

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
    nb_soutenances = sum(x[j, h, k, t].X for j in jours for h in heures for k in range(len(salles)) for t in range(len(etudiants)))
    print(f"📊 Nombre total de soutenances programmées : {int(nb_soutenances)}")
    """
    for j in jours:
        for h in heures:
            for k in range(len(salles)):
                for t in range(len(etudiants)):
                    if x[j, h, k, t].X > 0.5:
                        print(f"\n✅ Soutenance : Étudiant {t} en Salle {k}, Jour {j}, Heure {h}")
                        enseignants_affectes = []
                        for e in range(len(enseignants)):
                            for f in range(3):
                                if y[j, h, k, e, f].X > 0.5:
                                    role = ["Président", "Maître de mémoire", "Examinateur"][f]
                                    enseignants_affectes.append(f"👨‍🏫 Enseignant {enseignants[e].id} ({role})")
                        if enseignants_affectes:
                            print("   👥 Jury :", ", ".join(enseignants_affectes))
                        else:
                            print("   ⚠ Aucun enseignant affecté à cette soutenance !")
    """
    # ------------------------------- Génération d'un PDF récapitulatif --------------------------------------

    
    # ------------------------- Construction du dictionnaire de planification --------------------------------
    planning = {}
    defense_list = []
    
    # Calculer le nombre total de soutenances programmées (basé sur la variable x)
    nb_soutenances = sum(
        x[j, h, k, t].X 
        for j in jours 
        for h in heures 
        for k in range(len(salles)) 
        for t in range(len(etudiants))
    )
    
    # Construire la liste des défenses
    for j in jours:
        for h in heures:
            for k in range(len(salles)):
                for t in range(len(etudiants)):
                    if x[j, h, k, t].X > 0.5:
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
                        for e in range(len(enseignants)):
                            for f in range(3):
                                if y[j, h, k, e, f].X > 0.5:
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
    for e in range(len(enseignants)):
        # Pour chaque enseignant, on compte le nombre de fois où il est affecté à un rôle dans le planning
        count = sum(
            y[j, h, k, e, f].X 
            for j in jours 
            for h in heures 
            for k in range(len(salles)) 
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
    
    return planning




cp(data=data)


# Planification Automatique des Soutenances - Version avec Salles

## 📋 Description

Ce modèle vise à planifier automatiquement les soutenances à l'Institut de Formation et de Recherche en Informatique (IFRI) de l'Université de Abomey Calavi (UAC). L'objectif est d'affecter chaque étudiant à un créneau horaire dans une salle avec un jury composé de trois membres (Président, Maître de mémoire et Examinateur), tout en respectant les contraintes de disponibilité, de spécialité et de grade des enseignants, ainsi que la capacité limitée des salles. Le modèle minimise également les déplacements des enseignants entre les salles et leur temps d'attente.

---

## 📊 Modélisation Mathématique

### Ensembles

| Notation | Description |
|----------|-------------|
| $J$ | Jours de soutenance, $J = \{0, 1, 2, 3, 4\}$ (5 jours) |
| $H$ | Créneaux horaires, $H = \{0, 1, ..., 7\}$ (8 créneaux/jour) |
| $K$ | Ensemble des salles |
| $T$ | Ensemble des étudiants |
| $E$ | Ensemble des enseignants |
| $F$ | Rôles : $0$ = Président, $1$ = Maître mémoire, $2$ = Examinateur |

### Paramètres

| Notation | Description |
|----------|-------------|
| $g_e$ | Grade de l'enseignant $e$ (Ingénieur=1, Docteur=2, MA=3, MC=4, Professeur=5) |
| $g_{min}$ | Grade minimum pour président ($g_{min} = 2$) |
| $D^E_{e,j,h}$ | Disponibilité enseignant $e$ au jour $j$, heure $h$ |
| $D^K_{k,j,h}$ | Disponibilité salle $k$ au jour $j$, heure $h$ |
| $M_{t,e}$ | $= 1$ si enseignant $e$ est spécialiste du domaine de l'étudiant $t$ |
| $MM_{t,e}$ | $= 1$ si enseignant $e$ est le maître de mémoire de l'étudiant $t$ |

### Variables de Décision

#### Variables principales

| Variable | Type | Description |
|----------|------|-------------|
| $x_{j,h,k,t}$ | Binaire | $= 1$ si étudiant $t$ soutient jour $j$, heure $h$, salle $k$ |
| $y_{j,h,k,e,f}$ | Binaire | $= 1$ si enseignant $e$ a rôle $f$ jour $j$, heure $h$, salle $k$ |
| $g^{max}_{j,h,k}$ | Entier | Grade maximum dans le jury de la session $(j, h, k)$ |

#### Variables pour les déplacements

| Variable | Type | Description |
|----------|------|-------------|
| $z_{e,j,k}$ | Binaire | $= 1$ si enseignant $e$ intervient dans salle $k$ jour $j$ |
| $w_{e,j}$ | Continue | Nombre de salles en excès utilisées par enseignant $e$ jour $j$ |

#### Variables pour le temps d'attente

| Variable | Type | Description |
|----------|------|-------------|
| $a_{e,j,h}$ | Binaire | $= 1$ si enseignant $e$ intervient jour $j$, heure $h$ |
| $T^{min}_{e,j}$ | Continue | Première heure d'intervention |
| $T^{max}_{e,j}$ | Continue | Dernière heure d'intervention |
| $W_{e,j}$ | Continue | Temps d'attente |

#### Variables soft

| Variable | Type | Description |
|----------|------|-------------|
| $s_{j,k}$ | Continue | Dépassement du max 8 soutenances/salle/jour |

---

### Contraintes

#### 1. Unicité de soutenance
$$\sum_{j \in J} \sum_{h \in H} \sum_{k \in K} x_{j,h,k,t} \leq 1 \quad \forall t \in T$$

#### 2. Conflit horaire dans une salle (une seule soutenance par salle à la fois)
$$\sum_{t \in T} x_{j,h,k,t} \leq 1 \quad \forall j \in J, \forall h \in H, \forall k \in K$$

#### 3. Conflit horaire des enseignants
$$\sum_{k \in K} \sum_{f \in F} y_{j,h,k,e,f} \leq 1 \quad \forall e \in E, \forall j \in J, \forall h \in H$$

#### 4. Disponibilité des enseignants
$$y_{j,h,k,e,f} \leq D^E_{e,j,h} \quad \forall e, j, h, k, f$$

#### 5. Constitution du jury (3 membres)
$$\sum_{e \in E} \sum_{f \in F} y_{j,h,k,e,f} = 3 \cdot \sum_{t \in T} x_{j,h,k,t} \quad \forall j, h, k$$

#### 6. Un enseignant = un seul rôle par session
$$\sum_{f \in F} y_{j,h,k,e,f} \leq 1 \quad \forall e, j, h, k$$

#### 7. Un seul président par session
$$\sum_{e \in E} y_{j,h,k,e,0} \leq 1 \quad \forall j, h, k$$

#### 8. Maître de mémoire assigné
$$\sum_{e \in E} \sum_{t \in T} MM_{t,e} \cdot y_{j,h,k,e,1} \geq \sum_{t \in T} x_{j,h,k,t} \quad \forall j, h, k$$

#### 9. Examinateur spécialiste assigné
$$\sum_{e \in E} \sum_{t \in T} M_{t,e} \cdot y_{j,h,k,e,2} \geq \sum_{t \in T} x_{j,h,k,t} \quad \forall j, h, k$$

#### 10. Grade minimum du président
$$\sum_{e \in E} g_e \cdot y_{j,h,k,e,0} \geq g_{min} \cdot \sum_{t \in T} x_{j,h,k,t} \quad \forall j, h, k$$

#### 11. Président obligatoire si soutenance
$$\sum_{e \in E} y_{j,h,k,e,0} = \sum_{t \in T} x_{j,h,k,t} \quad \forall j, h, k$$

#### 12. Limite de soutenances par enseignant par jour
$$\sum_{h \in H} \sum_{k \in K} \sum_{f \in F} y_{j,h,k,e,f} \leq 4 \quad \forall e \in E, \forall j \in J$$

#### 13. Président = plus haut gradé
$$g^{max}_{j,h,k} \geq g_e \cdot y_{j,h,k,e,f} \quad \forall j, h, k, e, f$$
$$\sum_{e \in E} g_e \cdot y_{j,h,k,e,0} = g^{max}_{j,h,k} \quad \forall j, h, k$$

#### 14. Examinateur doit être spécialiste
$$\sum_{t \in T} M_{t,e} \cdot x_{j,h,k,t} \geq y_{j,h,k,e,2} \quad \forall j, h, k, e$$

#### 15. Présence du maître de mémoire
$$\sum_{e \in E} MM_{t,e} \cdot y_{j,h,k,e,1} + \sum_{e \in E : MM_{t,e}=0} y_{j,h,k,e,1} \geq x_{j,h,k,t} \quad \forall j, h, k, t$$

#### 16. Lien affectation → salle (pour pénalité déplacement)
$$y_{j,h,k,e,f} \leq z_{e,j,k} \quad \forall e, j, k, h, f$$

#### 17. Comptage des salles en excès
$$\sum_{k \in K} z_{e,j,k} - 1 \leq w_{e,j} \quad \forall e, j$$

#### 18. Contrainte soft : max 8 soutenances par salle par jour
$$\sum_{h \in H} \sum_{t \in T} x_{j,h,k,t} \leq 8 + s_{j,k} \quad \forall j, k$$

#### 19. Modélisation du temps d'attente (Big-M)
$$a_{e,j,h} = \sum_{k \in K} \sum_{f \in F} y_{j,h,k,e,f}$$
$$T^{min}_{e,j} \leq h + (1 - a_{e,j,h}) \cdot M$$
$$T^{max}_{e,j} \geq h - (1 - a_{e,j,h}) \cdot M$$
$$W_{e,j} \geq T^{max}_{e,j} - T^{min}_{e,j} + 1 - \sum_{h \in H} a_{e,j,h}$$

---

### Fonction Objectif

$$\max Z = \sum_{j,h,k,t} x_{j,h,k,t} - p_1 \sum_{j,k} s_{j,k} - p_2 \sum_{e,j} w_{e,j} - p_3 \sum_{e,j} W_{e,j}$$

Avec :
- $p_1 = 100$ : Pénalité pour dépassement du max 8 soutenances/salle/jour
- $p_2 = 10$ : Pénalité pour changement de salle
- $p_3 = 5$ : Pénalité pour temps d'attente

---

## 📁 Structure des Données

### Entrée (`simu.json`)

```json
{
  "students": [
    {
      "id": "string",
      "speciality": "string",
      "mm_id": "string",
      "diplome": "string"
    }
  ],
  "professeurs": [
    {
      "id": "string",
      "specialities": ["string"],
      "grade": "Ingénieur|Docteur|MA|MC|Professeur",
      "disponibilite": [[0|1, ...], [...], [...], [...], [...]]
    }
  ],
  "salles": [
    {
      "id": "string",
      "disponibilite": [[0|1, ...], [...], [...], [...], [...]]
    }
  ]
}
```

### Sortie

```json
{
  "Defense": [
    {
      "student_id": "string",
      "defenseJury": {
        "president_id": "string",
        "supervisor_id": "string",
        "examiner_id": "string"
      },
      "room_id": "string",
      "schedule": "int",
      "date": "int"
    }
  ],
  "metriques": {
    "total_soutenances": "int",
    "moyenne_soutenances": "float",
    "max_defenses": "float",
    "min_defenses": "float",
    "stdev_defenses": "float"
  }
}
```

---

## 🚀 Utilisation

```python
import json

# Charger les données
with open("simu.json", "r") as f:
    data = json.load(f)

# Exécuter l'optimisation
from gurobi_without_api import cp
planning = cp(data)

# Le résultat est retourné sous forme de dictionnaire
print(f"Soutenances planifiées: {planning['metriques']['total_soutenances']}")
```


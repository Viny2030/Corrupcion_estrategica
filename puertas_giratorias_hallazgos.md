# Investigación de puertas giratorias — funcionarios ligados a RIGI / Atucha III / VPU litio

Mecanismo IV del libro (Layer I — "Revolving Doors"): funcionarios que se mueven entre
cargos públicos con poder de decisión y empresas/actores privados vinculados a un
estado extranjero, antes o después de tomar decisiones que los benefician.

Metodología: se revisó la trayectoria pública (nombramientos, prensa especializada,
denuncias judiciales) de los funcionarios que efectivamente firman o deciden sobre los
tres nodos institucionales más expuestos del módulo: (1) Comité Evaluador de Proyectos
RIGI (litio chino), (2) NA-SA/CNEA (Atucha III, CNNC), (3) ENACOM (5G, Huawei). No se
encontró información pública sobre puertas giratorias en Defensa/armamento (vector sin
mecanismo materializado) ni en Institutos Confucio (no hay "funcionario decisor" único,
son convenios universitarios).

## 1. RIGI / litio — Secretaría de Minería (Luis Lucero)

Hallazgo confirmado, documentado y con relevancia directa para el vector
`litio-rigi-zijin-ganfeng`, aunque **no** vincula directamente a un actor chino:

- Luis Lucero, secretario de Minería desde abril de 2024, venía del estudio jurídico
  Marval O'Farrell Mairal, donde asesoró a Glencore, Rio Tinto, AngloGold Ashanti, Vale
  y Newmont — todas mineras occidentales, no SOEs chinas o rusas.
- Fue excusado formalmente (resolución del Ministerio de Economía) de intervenir en
  expedientes de Glencore Pachón, Minera Alumbrera/Agua Rica (MARA) y afines.
- En abril de 2026, la Asociación Argentina de Abogados/as Ambientalistas lo denunció
  penalmente sosteniendo que esa excusación "no fue efectiva": habría participado
  activamente en la reforma de la Ley de Glaciares, que flexibiliza zonas habilitadas
  para minería. Diputados de la oposición (Ferraro, del Pla, Selva) pidieron excluirlo
  del debate legislativo por el mismo motivo.
- Lucero integra el circuito que decide sobre solicitudes RIGI de litio, incluidas las
  de actores chinos: en julio de 2025 el Comité Evaluador RIGI rechazó el ingreso de
  Ganfeng (proyecto Mariana, Salta) por incumplir mínimos de inversión, mientras que
  Zijin sí accedió a incentivos RIGI para su proyecto (jul-2026, ver nota actualizada en
  `seed_vectores.json`).

**Clasificación bajo el framework NEST**: es un caso de manual del mecanismo IV
(revolving doors) en el nodo institucional correcto, pero el vínculo externo
documentado es con mineras occidentales, no con un estado extranjero rival (China/
Rusia) — por lo que **no** cumple el elemento de "external linkage" que exige el libro
para strategic corruption en el sentido de este módulo. Se registra como **antecedente
estructural a vigilar**, no como vector clasificable: si en el futuro Lucero interviene
en un expediente de Zijin o Ganfeng sin excusarse, o si aparece un vínculo laboral
posterior con alguna de esas empresas, eso sí activaría el classification test completo.

## 2. Atucha III / NA-SA / CNEA (CNNC)

Se revisaron los tres firmantes/participantes del contrato de 2022 y su prórroga:

- **José Luis Antúnez** (presidente de NA-SA): ingeniero electromecánico (UBA), en el
  sector nuclear desde los años 80 (NUCLAR S.A., montaje de Embalse). Presidió NA-SA
  2005-2015 y desde 2021. Sin trayectoria previa ni posterior en empresas chinas
  encontrada en fuentes públicas.
- **Jorge Sidelnik** (vicepresidente de NA-SA): sin antecedentes de vínculo con CNNC u
  otra empresa china hallados.
- **Diego Hurtado de Mendoza** (vicepresidente de CNEA 2021-2023, participó de la firma
  por CNEA): físico e historiador de la ciencia, con trayectoria académica y en gestión
  pública (ARN, Ministerio de Ciencia). Declaraciones públicas favorables al acuerdo con
  China ("tener a China como socio... es una ventana"), pero sin vínculo laboral o
  patrimonial documentado con CNNC antes o después del cargo.

**Resultado**: sin evidencia de puerta giratoria en el nodo Atucha III/CNNC. Esto no
descarta que exista — la opacidad de los términos de financiamiento del acuerdo
(señalada ya en `seed_vectores.json`) limita lo que puede verificarse con fuentes
abiertas. Se mantiene como vector a revisar en corridas futuras si trasciende
información societaria/patrimonial nueva.

## 3. ENACOM / 5G / Huawei

No se identificó un funcionario individual con poder de decisión final sobre el proceso
de licitación 5G (aún sin resolver, ver vector `5g-enacom-huawei`, reclasificado esta
corrida como `vigilar_sin_mecanismo_confirmado`). No corresponde investigación de
puertas giratorias hasta que exista una decisión concreta y un funcionario identificado
como responsable de ella.

## Conclusión y siguiente paso

No se encontró un caso confirmado de puerta giratoria entre el Estado argentino y un
actor estatal chino o ruso en los tres nodos revisados. El hallazgo de mayor relevancia
(Lucero) es un caso real y bien documentado de revolving door que **no** cumple el
criterio de vínculo con estado extranjero rival que exige el alcance de este módulo,
pero sí señala una vulnerabilidad institucional en el mismo comité que evalúa litio
chino — se agrega como antecedente de contexto en el vector `litio-rigi-zijin-ganfeng`
y como ítem de vigilancia continua (corrida semanal), no como un vector nuevo.

Fuentes:
- https://www.eldiarioar.com/politica/denuncian-penalmente-secretario-mineria-presunto-conflicto-intereses-ley-glaciares_1_13125406.html
- https://www.lanacion.com.ar/politica/el-gobierno-designo-a-luis-lucero-como-el-nuevo-secretario-de-mineria-de-la-nacion-nid25032024/
- https://www.ambito.com/energia/gobierno-aprobo-rigi-litio-galan-lithium-us271-millones-catamarca-y-rechazo-la-empresa-china-ganfeng-n6170403
- https://www.infobae.com/economia/2026/07/14/la-china-zijin-accede-a-incentivos-para-millonario-proyecto-de-litio-en-argentina/
- https://www.na-sa.com.ar/es/prensa/proyecto-central-nuclear-atucha-iii-declaracion-conjunta-262
- https://www.ambito.com/china/firmaron-contrato-la-cuarta-central-nuclear-atucha-iii-us8300-millones-n5362824

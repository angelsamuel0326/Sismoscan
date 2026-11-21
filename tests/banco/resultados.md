# Resultados de la evaluación con banco de imágenes

Imágenes evaluadas: 52 (semáforo: 16 · con grieta: 41 · controles sin grieta: 10).

## A. Detección local (OpenCV) · peor caso: foto libre, sin trazo del usuario

- Grietas detectadas: 40/41 (98 %).
- Falsos positivos en controles sin grieta: 2/10 (14.jpg, 15.jpg).
- Orientación correcta (entre las detectadas con orientación esperada definida): 27/33 (82 %).

## A2. Trazo del usuario sobre algo que NO es grieta (cable, marco)

- La detección local «confirma» una falsa grieta en 1/2 casos (n04.jpg). Límite conocido: no distingue una grieta de otra línea oscura; por eso la app exige que el usuario marque la grieta y confirme el resultado.

## B. Semáforo (motor de reglas)

- Coincidencia exacta: 13/16 (81 %).
- Dentro de ±1 nivel: 16/16 (100 %).
- Subestimaciones (resultado menos grave que el esperado): 0; de ellas, casos esperados en rojo: 0.
- Sobreestimaciones (más grave que el esperado): 3.

Matriz de confusión (filas = esperado, columnas = obtenido):

| Esperado \ Obtenido | Verde | Amarillo | Rojo |
|---|---|---|---|
| Verde | 0 | 3 | 0 |
| Amarillo | 0 | 9 | 0 |
| Rojo | 0 | 0 | 4 |

## Detalle por imagen

| Img | Esperado | Obtenido | Índice | Detectada | Orient. esperada | Orient. detectada |
|---|---|---|---|---|---|---|
| 01.jpg | verde | amarillo | 45 | si | vertical | vertical |
| 02.jpg | amarillo | amarillo | 45 | si | vertical | vertical |
| 03.jpg | amarillo | amarillo | 45 | si | n/a | diagonal |
| 05.jpg | amarillo | amarillo | 45 | si | vertical | vertical |
| 06.jpg | rojo | rojo | 60 | si | vertical | vertical |
| 07.jpg | amarillo | amarillo | 36 | si | diagonal | diagonal |
| 08.jpg | rojo | rojo | 60 | si | vertical | vertical |
| 09.jpg | amarillo | amarillo | 30 | si | vertical | horizontal |
| 10.jpg | amarillo | amarillo | 30 | si | diagonal | diagonal |
| 11.jpg | amarillo | amarillo | 45 | si | vertical | diagonal |
| 12.jpg | n/a | — | — | si | n/a | vertical |
| 13.jpg | verde | amarillo | 30 | si | vertical | vertical |
| 14.jpg | sin_grieta | — | — | si | n/a | vertical |
| 15.jpg | sin_grieta | — | — | si | n/a | diagonal |
| 16.jpg | verde | amarillo | 45 | si | n/a | horizontal |
| 17.jpg | amarillo | amarillo | 45 | si | horizontal | horizontal |
| 18.jpg | amarillo | amarillo | 30 | si | vertical | diagonal |
| 19.jpg | rojo | rojo | 60 | si | vertical | vertical |
| 20.jpg | rojo | rojo | 60 | si | vertical | diagonal |
| n01.jpg | sin_grieta | — | — | no | n/a | — |
| n02.jpg | sin_grieta | — | — | no | n/a | — |
| n03.jpg | sin_grieta | — | — | no | n/a | — |
| n04.jpg | sin_grieta | — | — | no | n/a | — |
| n05.jpg | sin_grieta | — | — | no | n/a | — |
| n06.jpg | sin_grieta | — | — | no | n/a | — |
| 21.jpg | n/a | — | — | si | diagonal | diagonal |
| 22.jpg | n/a | — | — | si | diagonal | diagonal |
| 23.jpg | n/a | — | — | si | diagonal | diagonal |
| 24.jpg | n/a | — | — | si | n/a | diagonal |
| 25.jpg | n/a | — | — | si | vertical | diagonal |
| 26.jpg | n/a | — | — | si | horizontal | horizontal |
| 27.jpg | n/a | — | — | si | horizontal | horizontal |
| 28.jpg | n/a | — | — | si | horizontal | horizontal |
| 29.jpg | n/a | — | — | si | vertical | vertical |
| n07.jpg | sin_grieta | — | — | no | n/a | — |
| n08.jpg | sin_grieta | — | — | no | n/a | — |
| 30.jpg | n/a | — | — | si | diagonal | diagonal |
| 31.jpg | n/a | — | — | si | vertical | vertical |
| 32.jpg | n/a | — | — | si | n/a | diagonal |
| 33.jpg | n/a | — | — | si | horizontal | horizontal |
| 34.jpg | n/a | — | — | si | horizontal | horizontal |
| 35.jpg | n/a | — | — | no | n/a | — |
| 36.jpg | n/a | — | — | si | n/a | horizontal |
| 37.jpg | n/a | — | — | si | n/a | horizontal |
| 38.jpg | n/a | — | — | si | horizontal | horizontal |
| 39.jpg | n/a | — | — | si | diagonal | diagonal |
| 40.jpg | n/a | — | — | si | horizontal | horizontal |
| 41.jpg | n/a | — | — | si | n/a | diagonal |
| 42.jpg | n/a | — | — | si | horizontal | horizontal |
| 43.jpg | n/a | — | — | si | vertical | diagonal |
| 44.jpg | n/a | — | — | si | vertical | vertical |
| 45.jpg | n/a | — | — | si | vertical | vertical |

> Las etiquetas esperadas son un criterio visual preliminar y las medidas sin escala son supuestos: los porcentajes indican consistencia, no exactitud estructural. Deben validarse con un ingeniero civil o estructural.
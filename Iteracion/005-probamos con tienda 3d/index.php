<!DOCTYPE html>
<html lang="es">
<head>
    <title>Pierodev</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body, html {
        padding: 0px;
        margin: 0px;
        font-family: 'Century Gothic', CenturyGothic, AppleGothic, sans-serif;
        background: #f3f4f6dc; /* Fondo gris suave para que destaquen las tarjetas */
    }
    header {
        background: linear-gradient(135deg, #1e3a8a, #0ea5e9);
        color: white;
        display: flex;
        align-items: center;
        padding: 10px 20px;
    }
    header h1 {
        margin: 0;
        font-size: 1.5rem;
    }
    header nav {
        flex-grow: 1;
        display: flex;
        justify-content: center;
    }
    header nav ul {
        display: flex;
        gap: 20px;
        list-style: none;
        padding: 0;
        margin: 0;
    }
    header a {
        color: inherit;
        text-decoration: none;
        font-size: 1.3em;
    }
    .search input {
        padding: 8px 15px;
        border-radius: 15px;
        border: none;
        outline: none;
        font-size: 1rem;
    }

    /* -------- REJILLA COMPLEJA CON FLEX SOLO EN MAIN -------- */

    main {
        display: flex;
        flex-wrap: wrap;         
        gap: 20px;               
        padding: 20px;
        box-sizing: border-box;
        max-width: 1200px;
        margin: 0 auto;
        align-items: stretch;
    }

    /* Tarjeta base */
    main article {
        border: 1px solid #dddddd;
        padding: 15px;
        box-sizing: border-box;
        flex: 1 1 100%;
        text-align: center;
        background: #ffffff;
        border-radius: 10px;

        display: flex;
        flex-direction: column;

        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.08);
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }

    main article:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.18);
        border-color: #0ea5e9;
    }

    /* Imágenes: tamaño uniforme con recorte elegante + zoom suave */
    main article img {
        width: 200px;
        height: 200px;
        object-fit: cover;
        display: block;
        margin: 0 auto 10px auto;
        transition: transform 0.25s ease; /* para el zoom */
    }

    /* Zoom de la imagen cuando se hace hover sobre la tarjeta */
    main article:hover img {
        transform: scale(1.03);
    }

    /* Título del producto */
    main article strong {
        display: block;
        font-size: 1.15rem;   /* un pelín más grande */
        margin-bottom: 6px;
    }

    /* Descripción */
    main article em {
        display: block;
        font-size: 0.9rem;
        color: #6b7280;       /* gris más suave */
        margin-bottom: 10px;
    }

    /* ========= META: MATERIAL, TAMAÑO, CATEGORÍA ========= */
    .product-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        justify-content: center;
        margin-bottom: 10px;
        font-size: 0.85rem;
    }

    article.destacado .product-meta {
        justify-content: flex-start;
    }

    .meta-tag {
        padding: 4px 8px;
        border-radius: 999px;
        background: #f3f4f6;
        color: #111827;
        white-space: nowrap;
    }

    .meta-label {
        font-weight: bold;
        color: #1e3a8a;
        margin-right: 2px;
    }

    .product-price-cta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;

        margin-top: auto;
        padding-top: 8px;
        border-top: 1px solid #e5e7eb;
    }

    .product-price {
        font-weight: bold;
        font-size: 1.05rem;    /* precio un poco más protagonista */
        color: #1e3a8a;
    }

    .btn-more {
        display: inline-block;
        padding: 6px 14px;
        border-radius: 999px;
        background: linear-gradient(135deg, #1e3a8a, #0ea5e9);
        color: #ffffff;
        text-decoration: none;
        font-size: 0.9rem;
        font-weight: bold;
        border: none;
    }

    .btn-more:hover {
        filter: brightness(1.05);
    }

    .btn-more:focus {
        outline: 2px solid #0ea5e9;
        outline-offset: 2px;
    }

    /* ======== TARJETA DESTACADA (PRODUCTO 1) ======== */

    main article.destacado {
        flex-basis: 100%;
        text-align: left;
        border-width: 2px;        /* borde más marcado */
        border-color: #0ea5e9;    /* azul acorde con la página */
    }

    .destacado-inner {
        display: flex;
        gap: 20px;
        align-items: stretch;
    }

    .destacado-img {
        flex: 0 0 40%;
        display: flex;
        justify-content: center;
        align-items: center;
    }

    .destacado-img img {
        width: 100%;
        max-width: 320px;
        height: 260px;
        object-fit: cover;
        margin: 0 auto;
    }

    .destacado-info {
        flex: 1;
        display: flex;
        flex-direction: column;
    }

    /* ======== REJILLA COMPLEJA (ANCHO DE CADA TARJETA) ======== */

    /* Producto 1 ya controlado con .destacado (100%) */

    /* Productos 2 y 3: dos tarjetas anchas (media fila cada una) */
    main article:nth-child(2),
    main article:nth-child(3) {
        flex-basis: calc(50% - 20px);
    }

    /* Productos 4, 5, 6 y 7: cuatro columnas */
    main article:nth-child(4),
    main article:nth-child(5),
    main article:nth-child(6),
    main article:nth-child(7) {
        flex-basis: calc(25% - 20px);
    }

    /* Productos 8 y 9: dos columnas anchas */
    main article:nth-child(8),
    main article:nth-child(9) {
        flex-basis: calc(50% - 20px);
    }

    /* RESPONSIVE */
    @media (max-width: 900px) {
        main article.destacado {
            flex-basis: 100%;
        }
        .destacado-inner {
            flex-direction: column;
        }
        .destacado-info {
            text-align: center;
        }

        main article:nth-child(2),
        main article:nth-child(3),
        main article:nth-child(4),
        main article:nth-child(5),
        main article:nth-child(6),
        main article:nth-child(7),
        main article:nth-child(8),
        main article:nth-child(9) {
            flex-basis: calc(50% - 20px);
        }
    }

    @media (max-width: 600px) {
        main article {
            flex-basis: 100%;
        }
        .product-price-cta {
            justify-content: center;
        }
    }

    footer {
        text-align: center;
        padding: 12px 0px;
        margin-top: 20px;
        font-size: 0.9rem;
        background: linear-gradient(135deg, #152a60, #0a70a0);
        color: white;
    }
    </style>
</head>
<body>
    <header>
        <h1>Pierodev | Impresiones 3D</h1>
        <nav>
            <ul>
                <li><a href="index.php">Inicio</a></li>
                <li><a href="nosotros.php">Nosotros</a></li>
                <li><a href="contacto.php">Contacto</a></li>
            </ul>
        </nav>
        <div class="search">
            <input type="text" placeholder="Buscar...">
        </div>
    </header>

    <main>
      <?php
        // Cargar el XML de productos 3D desde el archivo productos3d.xml
        // simplexml_load_file devuelve un objeto SimpleXMLElement con todos los nodos del XML
        $xml = simplexml_load_file("productos3d.xml");

        // Inicializamos un contador para saber en qué posición vamos (1, 2, 3...)
        // Esto se usa para aplicar el diseño especial al primer producto (destacado)
        $index = 0;

        // Recorremos cada nodo <producto> dentro del XML
        foreach ($xml->producto as $producto) {

            // Aumentamos el contador en 1 por cada producto
            $index++;

            // Convertimos cada campo del XML a string para trabajar más cómodo en PHP
            $nombre      = (string)$producto->nombre;
            $descripcion = (string)$producto->descripcion;
            $imagen      = (string)$producto->imagen;
            $enlace      = (string)$producto->enlace;    // Enlace a más detalles del producto
            $precio      = (string)$producto->precio;
            $material    = (string)$producto->material;
            $tamano      = (string)$producto->tamano;
            $categoria   = (string)$producto->categoria;

            // Si es el primer producto (index === 1), lo mostramos con el diseño "destacado"
            // - Imagen a la izquierda
            // - Información a la derecha
            // - Borde azul más marcado
            if ($index === 1) {
                echo "<article class='destacado'>";
                echo "  <div class='destacado-inner'>";

                // Columna izquierda: imagen grande del producto
                echo "    <div class='destacado-img'>";
                echo "      <img src='$imagen' alt='$nombre'>";
                echo "    </div>";

                // Columna derecha: nombre, descripción, meta y precio + botón
                echo "    <div class='destacado-info'>";
                echo "      <strong>$nombre</strong>";
                echo "      <em>$descripcion</em>";

                // Bloque de información adicional en formato "píldoras":
                // material, tamaño y categoría
                echo "      <div class='product-meta'>";
                echo "        <span class='meta-tag'><span class='meta-label'>Material:</span> $material</span>";
                echo "        <span class='meta-tag'><span class='meta-label'>Tamaño:</span> $tamano</span>";
                echo "        <span class='meta-tag'><span class='meta-label'>Categoría:</span> $categoria</span>";
                echo "      </div>";

                // Bloque inferior: precio + botón "Más información"
                echo "      <div class='product-price-cta'>";
                echo "        <span class='product-price'>Precio: $precio €</span>";
                echo "        <a class='btn-more' href='$enlace'>Más información</a>";
                echo "      </div>";

                echo "    </div>";   // cierre .destacado-info

                echo "  </div>";     // cierre .destacado-inner
                echo "</article>";

            } else {
                // Para el resto de productos usamos la tarjeta "normal"
                // que se adapta a la rejilla (2 columnas, 4 columnas, etc.)
                echo "<article>";

                // Imagen del producto
                echo "<img src='$imagen' alt='$nombre'>";

                // Nombre del producto
                echo "<strong>$nombre</strong>";

                // Descripción corta del producto
                echo "<em>$descripcion</em>";

                // Píldoras con material, tamaño y categoría
                echo "<div class='product-meta'>";
                echo "  <span class='meta-tag'><span class='meta-label'>Material:</span> $material</span>";
                echo "  <span class='meta-tag'><span class='meta-label'>Tamaño:</span> $tamano</span>";
                echo "  <span class='meta-tag'><span class='meta-label'>Categoría:</span> $categoria</span>";
                echo "</div>";

                // Zona inferior con precio y botón de acción
                echo "<div class='product-price-cta'>";
                echo "<span class='product-price'>Precio: $precio €</span>";
                echo "<a class='btn-more' href='$enlace'>Más información</a>";
                echo "</div>";

                echo "</article>";
            }
        }
      ?>
    </main>

    <footer>
        © <?php echo date("Y"); ?> Pierodev · Impresiones 3D
    </footer>
</body>
</html>

<?php
session_start();

$host = 'localhost';
$dbname = 'base_de_datos';
$username = 'root'; // O el nombre de usuario que uses
$password = ''; // La contraseña que uses (deja en blanco si no tienes)

try {
    // Conectar a la base de datos
    $conn = new PDO("mysql:host=$host;dbname=$dbname", $username, $password);
    $conn->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

    // Resto del código...
    if (isset($_POST['username']) && isset($_POST['password'])) {
        $username = $_POST['username'];
        $password = $_POST['password'];

        $stmt = $conn->prepare('SELECT * FROM estudiantes WHERE username = :username AND password = :password');
        $stmt->execute(['username' => $username, 'password' => $password]);
        $user = $stmt->fetch(PDO::FETCH_ASSOC);

        if ($user) {
            $_SESSION['user_id'] = $user['id'];
            header('Location: calificaciones.php');
            exit;
        } else {
            header('Location: error.html');
            exit;
        }
    }
} catch (PDOException $e) {
    echo 'Error: ' . $e->getMessage();
}
?>

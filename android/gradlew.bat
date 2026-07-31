@ECHO OFF
REM Gradle startup for Windows — prefer using Android Studio, or install JDK 17 + run gradlew.
SET DIR=%~dp0
java -classpath "%DIR%gradle\wrapper\gradle-wrapper.jar" org.gradle.wrapper.GradleWrapperMain %*

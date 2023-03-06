from src.compilers.kotlin import KotlinCompiler
from src.compilers.groovy import GroovyCompiler
from src.compilers.java import JavaCompiler
from src.compilers.scala import ScalaCompiler


COMPILERS = {
    'kotlin': KotlinCompiler,
    'groovy': GroovyCompiler,
    'java': JavaCompiler,
    'scala': ScalaCompiler
}

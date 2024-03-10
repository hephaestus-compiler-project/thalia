from src.translators.kotlin import KotlinTranslator
from src.translators.groovy import GroovyTranslator
from src.translators.scala import ScalaTranslator
from src.translators.java import JavaTranslator
from src.translators.swift import SwiftTranslator


TRANSLATORS = {
    'kotlin': KotlinTranslator,
    'groovy': GroovyTranslator,
    'java': JavaTranslator,
    'scala': ScalaTranslator,
    'swift': SwiftTranslator
}

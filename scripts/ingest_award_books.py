"""
Ingest high-quality children's books from curated award/classic lists.
- Google Books API for metadata (cover, description, page count, ISBN)
- Claude Haiku for learning goal classification
- Skips books already in DB; enriches metadata if missing

Run: DATABASE_URL="postgresql://..." ANTHROPIC_API_KEY="sk-..." python scripts/ingest_award_books.py
"""
import asyncio
import asyncpg
import httpx
import json
import os
import re
import time

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:eRrNwgeutWVANDhVskIKbCkOJXQhRIWn@viaduct.proxy.rlwy.net:33806/railway"
).replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_BOOKS_KEY = os.getenv("GOOGLE_BOOKS_API_KEY", "")

VALID_GOALS = [
    "kindness", "courage", "friendship", "emotions", "science",
    "history", "diversity", "resilience", "problem_solving",
    "environment", "family", "creativity"
]

# ── Curated Book List ─────────────────────────────────────────────────────────
# Format: (title, author, age_min, age_max, [goals], [awards])
# Goals are pre-seeded; Claude will validate/extend from the description.

CURATED_BOOKS = [
    # ── Newbery Medal Winners ──────────────────────────────────────────────────
    ("The Giver", "Lois Lowry", 10, 14, ["courage", "history", "problem_solving"], ["Newbery Medal 1994"]),
    ("Holes", "Louis Sachar", 9, 12, ["friendship", "resilience", "history"], ["Newbery Medal 1999"]),
    ("Bud, Not Buddy", "Christopher Paul Curtis", 9, 12, ["resilience", "family", "history"], ["Newbery Medal 2000"]),
    ("A Single Shard", "Linda Sue Park", 9, 12, ["resilience", "creativity", "history"], ["Newbery Medal 2002"]),
    ("The Tale of Despereaux", "Kate DiCamillo", 7, 11, ["courage", "kindness", "friendship"], ["Newbery Medal 2004"]),
    ("Kira-Kira", "Cynthia Kadohata", 9, 12, ["family", "resilience", "history"], ["Newbery Medal 2005"]),
    ("The Graveyard Book", "Neil Gaiman", 10, 14, ["courage", "family", "friendship"], ["Newbery Medal 2009"]),
    ("When You Reach Me", "Rebecca Stead", 9, 12, ["friendship", "problem_solving", "courage"], ["Newbery Medal 2010"]),
    ("Moon Over Manifest", "Clare Vanderpool", 9, 12, ["history", "resilience", "friendship"], ["Newbery Medal 2011"]),
    ("The One and Only Ivan", "Katherine Applegate", 8, 12, ["courage", "friendship", "environment"], ["Newbery Medal 2013"]),
    ("Flora & Ulysses", "Kate DiCamillo", 8, 12, ["creativity", "family", "kindness"], ["Newbery Medal 2014"]),
    ("The Crossover", "Kwame Alexander", 9, 12, ["family", "resilience", "emotions"], ["Newbery Medal 2015"]),
    ("Last Stop on Market Street", "Matt de la Peña", 4, 8, ["kindness", "diversity", "family"], ["Newbery Medal 2016"]),
    ("Hello, Universe", "Erin Entrada Kelly", 8, 12, ["friendship", "courage", "diversity"], ["Newbery Medal 2018"]),
    ("Merci Suarez Changes Gears", "Meg Medina", 9, 12, ["family", "resilience", "diversity"], ["Newbery Medal 2019"]),
    ("New Kid", "Jerry Craft", 8, 12, ["diversity", "friendship", "courage"], ["Newbery Medal 2020"]),
    ("When You Trap a Tiger", "Tae Keller", 8, 12, ["family", "courage", "creativity"], ["Newbery Medal 2021"]),
    ("The Last Cuentista", "Donna Barba Higuera", 9, 12, ["courage", "family", "creativity"], ["Newbery Medal 2022"]),
    ("Freewater", "Amina Luqman-Dawson", 9, 12, ["history", "courage", "resilience"], ["Newbery Medal 2023"]),
    ("The Eyes and the Impossible", "Dave Eggers", 8, 12, ["friendship", "courage", "environment"], ["Newbery Medal 2024"]),

    # ── Newbery Honor / Notable ────────────────────────────────────────────────
    ("Number the Stars", "Lois Lowry", 9, 12, ["courage", "history", "friendship"], ["Newbery Medal 1990"]),
    ("Maniac Magee", "Jerry Spinelli", 9, 12, ["diversity", "resilience", "kindness"], ["Newbery Medal 1991"]),
    ("Shiloh", "Phyllis Reynolds Naylor", 8, 12, ["courage", "kindness", "family"], ["Newbery Medal 1992"]),
    ("Missing May", "Cynthia Rylant", 9, 12, ["family", "resilience", "emotions"], ["Newbery Medal 1993"]),
    ("Walk Two Moons", "Sharon Creech", 9, 12, ["family", "resilience", "emotions"], ["Newbery Medal 1995"]),
    ("The Midwife's Apprentice", "Karen Cushman", 9, 12, ["resilience", "history", "courage"], ["Newbery Medal 1996"]),
    ("The View from Saturday", "E.L. Konigsburg", 9, 12, ["friendship", "problem_solving", "kindness"], ["Newbery Medal 1997"]),
    ("Out of the Dust", "Karen Hesse", 9, 12, ["resilience", "history", "family"], ["Newbery Medal 1998"]),
    ("Esperanza Rising", "Pam Muñoz Ryan", 8, 12, ["resilience", "family", "history"], ["Pura Belpré Award"]),
    ("Island of the Blue Dolphins", "Scott O'Dell", 9, 12, ["resilience", "courage", "environment"], ["Newbery Medal 1961"]),
    ("It's Like This, Cat", "Emily Cheney Neville", 9, 12, ["family", "emotions", "friendship"], ["Newbery Medal 1964"]),
    ("Shadow of a Bull", "Maia Wojciechowska", 9, 12, ["courage", "resilience", "history"], ["Newbery Medal 1965"]),
    ("From the Mixed-Up Files of Mrs. Basil E. Frankweiler", "E.L. Konigsburg", 9, 12, ["problem_solving", "courage", "creativity"], ["Newbery Medal 1968"]),
    ("Sounder", "William H. Armstrong", 9, 13, ["resilience", "family", "history"], ["Newbery Medal 1970"]),
    ("Mrs. Frisby and the Rats of NIMH", "Robert C. O'Brien", 9, 12, ["courage", "science", "problem_solving"], ["Newbery Medal 1972"]),
    ("Julie of the Wolves", "Jean Craighead George", 9, 13, ["resilience", "environment", "courage"], ["Newbery Medal 1973"]),
    ("The Slave Dancer", "Paula Fox", 10, 14, ["history", "courage", "resilience"], ["Newbery Medal 1974"]),
    ("M.C. Higgins, the Great", "Virginia Hamilton", 9, 12, ["family", "environment", "resilience"], ["Newbery Medal 1975"]),
    ("The Grey King", "Susan Cooper", 9, 12, ["courage", "problem_solving", "family"], ["Newbery Medal 1976"]),
    ("Roll of Thunder, Hear My Cry", "Mildred D. Taylor", 9, 13, ["history", "courage", "family"], ["Newbery Medal 1977"]),
    ("Bridge to Terabithia", "Katherine Paterson", 9, 12, ["friendship", "emotions", "resilience"], ["Newbery Medal 1978"]),
    ("The Westing Game", "Ellen Raskin", 9, 13, ["problem_solving", "friendship", "diversity"], ["Newbery Medal 1979"]),
    ("A Gathering of Days", "Joan W. Blos", 9, 12, ["history", "family", "courage"], ["Newbery Medal 1980"]),
    ("Jacob Have I Loved", "Katherine Paterson", 9, 13, ["family", "resilience", "emotions"], ["Newbery Medal 1981"]),
    ("A Visit to William Blake's Inn", "Nancy Willard", 6, 10, ["creativity", "courage", "family"], ["Newbery Medal 1982"]),
    ("Dicey's Song", "Cynthia Voigt", 9, 13, ["family", "resilience", "courage"], ["Newbery Medal 1983"]),
    ("Dear Mr. Henshaw", "Beverly Cleary", 8, 12, ["emotions", "family", "resilience"], ["Newbery Medal 1984"]),
    ("The Hero and the Crown", "Robin McKinley", 10, 14, ["courage", "history", "problem_solving"], ["Newbery Medal 1985"]),
    ("Sarah, Plain and Tall", "Patricia MacLachlan", 7, 11, ["family", "resilience", "kindness"], ["Newbery Medal 1986"]),
    ("The Whipping Boy", "Sid Fleischman", 8, 12, ["friendship", "courage", "resilience"], ["Newbery Medal 1987"]),
    ("Lincoln: A Photobiography", "Russell Freedman", 9, 13, ["history", "courage", "resilience"], ["Newbery Medal 1988"]),
    ("Joyful Noise: Poems for Two Voices", "Paul Fleischman", 8, 12, ["creativity", "environment", "science"], ["Newbery Medal 1989"]),
    ("Maniac Magee", "Jerry Spinelli", 9, 12, ["diversity", "resilience", "kindness"], ["Newbery Medal 1991"]),
    ("Hatchet", "Gary Paulsen", 9, 12, ["resilience", "courage", "environment"], ["Newbery Honor 1988"]),
    ("Tuck Everlasting", "Natalie Babbitt", 9, 12, ["family", "courage", "history"], []),
    ("A Long Walk to Water", "Linda Sue Park", 9, 13, ["resilience", "courage", "history"], []),

    # ── Caldecott Medal & Honor (Picture Books) ───────────────────────────────
    ("Where the Wild Things Are", "Maurice Sendak", 3, 8, ["emotions", "creativity", "family"], ["Caldecott Medal 1964"]),
    ("The Snowy Day", "Ezra Jack Keats", 3, 6, ["diversity", "creativity", "family"], ["Caldecott Medal 1963"]),
    ("Jumanji", "Chris Van Allsburg", 5, 9, ["courage", "problem_solving", "creativity"], ["Caldecott Medal 1982"]),
    ("The Polar Express", "Chris Van Allsburg", 4, 8, ["courage", "creativity", "family"], ["Caldecott Medal 1986"]),
    ("Owl Moon", "Jane Yolen", 3, 7, ["family", "environment", "creativity"], ["Caldecott Medal 1988"]),
    ("Tuesday", "David Wiesner", 3, 7, ["creativity", "problem_solving"], ["Caldecott Medal 1992"]),
    ("Smoky Night", "Eve Bunting", 5, 9, ["diversity", "kindness", "family"], ["Caldecott Medal 1995"]),
    ("Officer Buckle and Gloria", "Peggy Rathmann", 4, 8, ["friendship", "problem_solving", "kindness"], ["Caldecott Medal 1996"]),
    ("Snowflake Bentley", "Jacqueline Briggs Martin", 5, 9, ["science", "resilience", "creativity"], ["Caldecott Medal 1999"]),
    ("Joseph Had a Little Overcoat", "Simms Taback", 3, 7, ["creativity", "resilience", "family"], ["Caldecott Medal 2000"]),
    ("So You Want to Be President?", "Judith St. George", 6, 10, ["history", "courage", "creativity"], ["Caldecott Medal 2001"]),
    ("The Three Pigs", "David Wiesner", 4, 8, ["creativity", "problem_solving", "courage"], ["Caldecott Medal 2002"]),
    ("The Man Who Walked Between the Towers", "Mordicai Gerstein", 5, 9, ["courage", "creativity", "resilience"], ["Caldecott Medal 2004"]),
    ("Kitten's First Full Moon", "Kevin Henkes", 2, 5, ["emotions", "family", "resilience"], ["Caldecott Medal 2005"]),
    ("Flotsam", "David Wiesner", 4, 8, ["creativity", "science", "environment"], ["Caldecott Medal 2007"]),
    ("The House in the Night", "Susan Marie Swanson", 2, 5, ["family", "creativity", "emotions"], ["Caldecott Medal 2009"]),
    ("The Lion & the Mouse", "Jerry Pinkney", 3, 7, ["kindness", "friendship", "courage"], ["Caldecott Medal 2010"]),
    ("A Ball for Daisy", "Chris Raschka", 2, 5, ["emotions", "friendship", "resilience"], ["Caldecott Medal 2012"]),
    ("This Is Not My Hat", "Jon Klassen", 3, 7, ["courage", "problem_solving"], ["Caldecott Medal 2013"]),
    ("Locomotive", "Brian Floca", 6, 10, ["history", "science", "creativity"], ["Caldecott Medal 2014"]),
    ("The Adventures of Beekle: The Unimaginary Friend", "Dan Santat", 4, 8, ["creativity", "courage", "friendship"], ["Caldecott Medal 2015"]),
    ("Finding Winnie: The True Story of the World's Most Famous Bear", "Lindsay Mattick", 4, 8, ["family", "courage", "history"], ["Caldecott Medal 2016"]),
    ("Radiant Child: The Story of Young Artist Jean-Michel Basquiat", "Javaka Steptoe", 5, 9, ["creativity", "diversity", "resilience"], ["Caldecott Medal 2017"]),
    ("Wolf in the Snow", "Matthew Cordell", 4, 8, ["kindness", "courage", "environment"], ["Caldecott Medal 2018"]),
    ("Hello Lighthouse", "Sophie Blackall", 4, 8, ["family", "resilience", "history"], ["Caldecott Medal 2019"]),
    ("The Undefeated", "Kwame Alexander", 5, 10, ["history", "resilience", "diversity"], ["Caldecott Medal 2020"]),
    ("We Are Water Protectors", "Carole Lindstrom", 4, 8, ["environment", "courage", "diversity"], ["Caldecott Medal 2021"]),
    ("Watercress", "Andrea Wang", 4, 8, ["family", "diversity", "resilience"], ["Caldecott Medal 2022"]),
    ("Fry Bread: A Native American Family Story", "Kevin Noble Maillard", 4, 8, ["family", "diversity", "history"], ["Caldecott Honor 2020"]),
    ("When Stars Are Scattered", "Victoria Jamieson", 8, 12, ["resilience", "history", "family"], ["Schneider Family Book Award"]),
    ("Eyes That Kiss in the Corners", "Joanna Ho", 3, 7, ["diversity", "family", "kindness"], []),

    # ── Classic Children's Literature ─────────────────────────────────────────
    ("Charlotte's Web", "E.B. White", 7, 11, ["friendship", "kindness", "family"], []),
    ("Stuart Little", "E.B. White", 6, 10, ["courage", "family", "creativity"], []),
    ("The Trumpet of the Swan", "E.B. White", 7, 11, ["courage", "creativity", "resilience"], []),
    ("Harriet the Spy", "Louise Fitzhugh", 8, 12, ["courage", "friendship", "emotions"], []),
    ("A Cricket in Times Square", "George Selden", 7, 11, ["friendship", "creativity", "family"], []),
    ("The Wind in the Willows", "Kenneth Grahame", 7, 11, ["friendship", "family", "environment"], []),
    ("The Secret Garden", "Frances Hodgson Burnett", 8, 12, ["resilience", "family", "environment"], []),
    ("Mary Poppins", "P.L. Travers", 6, 10, ["creativity", "family", "courage"], []),
    ("Pippi Longstocking", "Astrid Lindgren", 6, 10, ["courage", "creativity", "friendship"], []),
    ("The Little Prince", "Antoine de Saint-Exupéry", 8, 12, ["friendship", "emotions", "creativity"], []),
    ("Alice's Adventures in Wonderland", "Lewis Carroll", 7, 12, ["creativity", "courage", "problem_solving"], []),
    ("The Wizard of Oz", "L. Frank Baum", 6, 10, ["courage", "friendship", "family"], []),
    ("Peter Pan", "J.M. Barrie", 6, 10, ["creativity", "courage", "family"], []),
    ("Treasure Island", "Robert Louis Stevenson", 9, 14, ["courage", "problem_solving", "history"], []),
    ("Robin Hood", "Howard Pyle", 9, 14, ["courage", "history", "resilience"], []),
    ("The Count of Monte Cristo (abridged)", "Alexandre Dumas", 10, 14, ["resilience", "courage", "history"], []),
    ("Swiss Family Robinson", "Johann David Wyss", 8, 13, ["family", "courage", "environment"], []),
    ("Robinson Crusoe", "Daniel Defoe", 10, 14, ["resilience", "courage", "environment"], []),
    ("The Phantom Tollbooth", "Norton Juster", 8, 12, ["creativity", "problem_solving", "courage"], []),
    ("A Wrinkle in Time", "Madeleine L'Engle", 9, 13, ["science", "courage", "family"], ["Newbery Medal 1963"]),
    ("James and the Giant Peach", "Roald Dahl", 7, 11, ["creativity", "courage", "resilience"], []),
    ("Charlie and the Chocolate Factory", "Roald Dahl", 7, 11, ["creativity", "courage", "kindness"], []),
    ("Matilda", "Roald Dahl", 7, 11, ["courage", "resilience", "creativity"], []),
    ("The BFG", "Roald Dahl", 6, 10, ["courage", "friendship", "creativity"], []),
    ("Danny the Champion of the World", "Roald Dahl", 7, 11, ["family", "courage", "resilience"], []),
    ("Fantastic Mr Fox", "Roald Dahl", 5, 9, ["family", "problem_solving", "courage"], []),
    ("The Witches", "Roald Dahl", 7, 11, ["courage", "family", "problem_solving"], []),
    ("George's Marvellous Medicine", "Roald Dahl", 5, 9, ["creativity", "family", "problem_solving"], []),

    # ── Popular Series (Book 1) ────────────────────────────────────────────────
    ("Percy Jackson and the Lightning Thief", "Rick Riordan", 9, 12, ["courage", "friendship", "problem_solving"], []),
    ("Diary of a Wimpy Kid", "Jeff Kinney", 8, 12, ["friendship", "problem_solving", "emotions"], []),
    ("Dog Man", "Dav Pilkey", 6, 10, ["courage", "friendship", "problem_solving"], []),
    ("Big Nate: In a Class by Himself", "Lincoln Peirce", 8, 12, ["friendship", "resilience", "problem_solving"], []),
    ("Captain Underpants and the Perilous Plot of Professor Poopypants", "Dav Pilkey", 6, 10, ["courage", "friendship", "problem_solving"], []),
    ("Magic Tree House: Dinosaurs Before Dark", "Mary Pope Osborne", 6, 9, ["science", "history", "courage"], []),
    ("Junie B. Jones and the Stupid Smelly Bus", "Barbara Park", 5, 8, ["emotions", "courage", "friendship"], []),
    ("Cam Jansen and the Mystery of the Stolen Diamonds", "David A. Adler", 6, 9, ["problem_solving", "friendship", "courage"], []),
    ("Nate the Great", "Marjorie Weinman Sharmat", 5, 8, ["problem_solving", "friendship", "courage"], []),
    ("Encyclopedia Brown, Boy Detective", "Donald J. Sobol", 7, 11, ["problem_solving", "courage", "friendship"], []),
    ("The Boxcar Children", "Gertrude Chandler Warner", 6, 10, ["family", "problem_solving", "resilience"], []),
    ("Geronimo Stilton: Lost Treasure of the Emerald Eye", "Geronimo Stilton", 6, 9, ["friendship", "courage", "problem_solving"], []),
    ("Ivy and Bean", "Annie Barrows", 5, 8, ["friendship", "kindness", "problem_solving"], []),
    ("Clementine", "Sara Pennypacker", 7, 10, ["friendship", "emotions", "family"], []),
    ("Ramona the Pest", "Beverly Cleary", 6, 10, ["emotions", "family", "courage"], []),
    ("Henry Huggins", "Beverly Cleary", 7, 11, ["family", "friendship", "problem_solving"], []),
    ("The Penderwicks", "Jeanne Birdsall", 8, 12, ["family", "friendship", "resilience"], ["National Book Award"]),
    ("The Mysterious Benedict Society", "Trenton Lee Stewart", 9, 13, ["problem_solving", "friendship", "courage"], []),
    ("The Invention of Hugo Cabret", "Brian Selznick", 9, 12, ["creativity", "history", "resilience"], ["Caldecott Medal 2008"]),

    # ── Picture Books & Early Readers ────────────────────────────────────────────
    ("Goodnight Moon", "Margaret Wise Brown", 1, 5, ["family", "emotions"], []),
    ("The Very Hungry Caterpillar", "Eric Carle", 2, 5, ["science", "creativity"], []),
    ("Guess How Much I Love You", "Sam McBratney", 2, 5, ["family", "emotions", "kindness"], []),
    ("The Very Lonely Firefly", "Eric Carle", 2, 5, ["friendship", "emotions"], []),
    ("Chrysanthemum", "Kevin Henkes", 4, 8, ["kindness", "emotions", "friendship"], []),
    ("Chester's Way", "Kevin Henkes", 4, 8, ["friendship", "diversity", "kindness"], []),
    ("Lilly's Purple Plastic Purse", "Kevin Henkes", 4, 8, ["emotions", "family", "friendship"], []),
    ("Owen", "Kevin Henkes", 3, 6, ["family", "emotions", "resilience"], []),
    ("Wemberly Worried", "Kevin Henkes", 3, 7, ["emotions", "courage", "friendship"], []),
    ("Julius, the Baby of the World", "Kevin Henkes", 3, 7, ["family", "emotions", "kindness"], []),
    ("Amos & Boris", "William Steig", 4, 8, ["friendship", "kindness", "courage"], []),
    ("Sylvester and the Magic Pebble", "William Steig", 4, 8, ["family", "problem_solving", "emotions"], []),
    ("Doctor De Soto", "William Steig", 4, 8, ["problem_solving", "courage", "kindness"], []),
    ("The Courage of Sarah Noble", "Alice Dalgliesh", 6, 10, ["courage", "history", "family"], ["Newbery Honor 1955"]),
    ("Frog and Toad Are Friends", "Arnold Lobel", 5, 8, ["friendship", "kindness", "emotions"], ["Caldecott Honor 1971"]),
    ("Frog and Toad Together", "Arnold Lobel", 5, 8, ["friendship", "courage", "kindness"], ["Newbery Honor 1973"]),
    ("Corduroy", "Don Freeman", 2, 6, ["friendship", "family", "emotions"], []),
    ("The Berenstain Bears and the Trouble with Friends", "Stan Berenstain", 3, 7, ["friendship", "kindness", "emotions"], []),
    ("If You Give a Mouse a Cookie", "Laura Numeroff", 3, 6, ["creativity", "family", "problem_solving"], []),
    ("The Stinky Cheese Man and Other Fairly Stupid Tales", "Jon Scieszka", 5, 9, ["creativity", "problem_solving"], []),
    ("Knuffle Bunny: A Cautionary Tale", "Mo Willems", 2, 6, ["family", "emotions", "resilience"], ["Caldecott Honor 2005"]),
    ("Don't Let the Pigeon Drive the Bus!", "Mo Willems", 2, 6, ["problem_solving", "emotions"], ["Caldecott Honor 2004"]),
    ("Elephant and Piggie: We Are in a Book!", "Mo Willems", 4, 8, ["friendship", "emotions", "creativity"], []),
    ("Scaredy Squirrel", "Mélanie Watt", 4, 8, ["courage", "emotions", "problem_solving"], []),
    ("Diary of a Worm", "Doreen Cronin", 4, 8, ["creativity", "science", "family"], []),
    ("Click, Clack, Moo: Cows That Type", "Doreen Cronin", 4, 8, ["problem_solving", "creativity", "kindness"], ["Caldecott Honor 2001"]),
    ("Stellaluna", "Janell Cannon", 4, 8, ["diversity", "family", "friendship"], []),
    ("Anansi the Spider: A Tale from the Ashanti", "Gerald McDermott", 4, 8, ["creativity", "problem_solving", "family"], ["Caldecott Honor 1973"]),
    ("Lon Po Po: A Red-Riding Hood Story from China", "Ed Young", 4, 8, ["courage", "family", "problem_solving"], ["Caldecott Medal 1990"]),
    ("Mufaro's Beautiful Daughters", "John Steptoe", 4, 8, ["kindness", "diversity", "resilience"], ["Caldecott Honor 1988"]),
    ("Amazing Grace", "Mary Hoffman", 5, 8, ["courage", "resilience", "diversity"], []),
    ("The Name Jar", "Yangsook Choi", 5, 9, ["diversity", "courage", "friendship"], []),
    ("Each Kindness", "Jacqueline Woodson", 5, 9, ["kindness", "emotions", "friendship"], []),
    ("Each Little Bird That Sings", "Deborah Wiles", 8, 12, ["family", "resilience", "emotions"], ["Newbery Honor 2006"]),
    ("Enemy Pie", "Derek Munson", 4, 8, ["kindness", "friendship", "problem_solving"], []),
    ("Enemy Pie", "Derek Munson", 4, 8, ["kindness", "friendship"], []),
    ("The Recess Queen", "Alexis O'Neill", 4, 8, ["kindness", "courage", "friendship"], []),
    ("Stand in My Shoes", "Bob Sornson", 4, 8, ["kindness", "diversity", "emotions"], []),
    ("Those Shoes", "Maribeth Boelts", 4, 8, ["kindness", "family", "resilience"], []),
    ("One", "Kathryn Otoshi", 3, 7, ["courage", "kindness", "diversity"], []),
    ("Zero", "Kathryn Otoshi", 3, 7, ["resilience", "kindness", "courage"], []),
    ("Beautiful Oops!", "Barney Saltzberg", 3, 7, ["creativity", "resilience", "emotions"], []),
    ("Ish", "Peter H. Reynolds", 4, 8, ["creativity", "resilience", "emotions"], []),
    ("The Dot", "Peter H. Reynolds", 4, 8, ["creativity", "resilience", "courage"], []),
    ("Sky Color", "Peter H. Reynolds", 4, 8, ["creativity", "problem_solving"], []),
    ("Rosie Revere, Engineer", "Andrea Beaty", 4, 8, ["science", "resilience", "creativity"], []),
    ("Iggy Peck, Architect", "Andrea Beaty", 4, 8, ["science", "creativity", "courage"], []),
    ("Ada Twist, Scientist", "Andrea Beaty", 4, 8, ["science", "curiosity", "creativity"], []),
    ("The Questioneers Picture Book Collection", "Andrea Beaty", 4, 8, ["science", "creativity", "problem_solving"], []),
    ("Counting by 7s", "Holly Goldberg Sloan", 9, 12, ["resilience", "friendship", "science"], []),
    ("The Wild Robot", "Peter Brown", 8, 12, ["science", "resilience", "family"], []),
    ("The Wild Robot Escapes", "Peter Brown", 8, 12, ["family", "resilience", "science"], []),

    # ── STEM & Science ────────────────────────────────────────────────────────
    ("Hidden Figures Young Readers Edition", "Margot Lee Shetterly", 9, 13, ["history", "science", "diversity"], []),
    ("Women in Science: 50 Fearless Pioneers", "Rachel Ignotofsky", 8, 14, ["science", "diversity", "history"], []),
    ("I Am Albert Einstein", "Brad Meltzer", 4, 8, ["science", "resilience", "creativity"], []),
    ("Who Was Albert Einstein?", "Jess M. Brallier", 8, 12, ["science", "history", "resilience"], []),
    ("Who Was Marie Curie?", "Megan Stine", 8, 12, ["science", "history", "resilience"], []),
    ("George's Secret Key to the Universe", "Lucy Hawking", 7, 11, ["science", "friendship", "courage"], []),
    ("The Magic School Bus: Lost in the Solar System", "Joanna Cole", 6, 10, ["science", "creativity", "problem_solving"], []),
    ("Hilo Book 1: The Boy Who Crashed to Earth", "Judd Winick", 7, 11, ["friendship", "science", "courage"], []),
    ("Nathan Hale's Hazardous Tales: One Dead Spy", "Nathan Hale", 8, 12, ["history", "courage", "problem_solving"], []),

    # ── History & Culture ─────────────────────────────────────────────────────
    ("Inside Out and Back Again", "Thanhha Lai", 8, 12, ["resilience", "diversity", "family"], ["Newbery Honor 2012"]),
    ("Front Desk", "Kelly Yang", 8, 12, ["diversity", "resilience", "family"], []),
    ("Three Keys", "Kelly Yang", 8, 12, ["diversity", "resilience", "courage"], []),
    ("Good Talk: A Memoir in Conversations", "Mira Jacob", 8, 12, ["diversity", "family", "history"], []),
    ("Stamped: Racism, Antiracism, and You", "Jason Reynolds", 10, 14, ["history", "diversity", "courage"], []),
    ("Genesis Begins Again", "Alicia D. Williams", 9, 12, ["diversity", "resilience", "family"], ["Newbery Honor 2020"]),
    ("American Street", "Ibi Zoboi", 12, 16, ["diversity", "family", "resilience"], []),
    ("The Watsons Go to Birmingham—1963", "Christopher Paul Curtis", 9, 12, ["history", "family", "courage"], ["Newbery Honor 1996"]),
    ("Bud, Not Buddy", "Christopher Paul Curtis", 9, 12, ["resilience", "family", "history"], ["Newbery Medal 2000"]),
    ("Locomotion", "Jacqueline Woodson", 9, 12, ["family", "resilience", "creativity"], ["Newbery Honor 2004"]),
    ("Brown Girl Dreaming", "Jacqueline Woodson", 9, 13, ["history", "family", "diversity"], ["Newbery Honor 2015"]),
    ("Show Way", "Jacqueline Woodson", 5, 9, ["history", "family", "diversity"], ["Caldecott Honor 2006"]),

    # ── Social Emotional / Feelings ───────────────────────────────────────────
    ("The Invisible String", "Patrice Karst", 3, 8, ["family", "emotions", "kindness"], []),
    ("When Sophie Gets Angry—Really, Really Angry", "Molly Bang", 3, 7, ["emotions", "family", "resilience"], ["Caldecott Honor 2000"]),
    ("In My Heart: A Book of Feelings", "Jo Witek", 2, 6, ["emotions", "family"], []),
    ("The Feelings Book", "Todd Parr", 2, 6, ["emotions", "diversity"], []),
    ("Today I Feel Silly, and Other Moods That Make My Day", "Jamie Lee Curtis", 3, 7, ["emotions", "family"], []),
    ("Grumpy Monkey", "Suzanne Lang", 3, 7, ["emotions", "friendship", "resilience"], []),
    ("Listening to My Body", "Gabi Garcia", 4, 8, ["emotions", "resilience", "kindness"], []),
    ("The Invisible String", "Patrice Karst", 3, 8, ["family", "emotions", "kindness"], []),
    ("Wonder", "R.J. Palacio", 8, 12, ["kindness", "friendship", "courage"], []),
    ("Restart", "Gordon Korman", 8, 12, ["kindness", "friendship", "resilience"], []),
    ("The One and Only Bob", "Katherine Applegate", 8, 12, ["friendship", "courage", "environment"], []),
    ("Ghost", "Jason Reynolds", 9, 13, ["resilience", "family", "friendship"], []),
    ("Patina", "Jason Reynolds", 9, 13, ["resilience", "family", "friendship"], []),
    ("Sunny", "Jason Reynolds", 9, 13, ["resilience", "family", "emotions"], []),
    ("Lu", "Jason Reynolds", 9, 13, ["resilience", "diversity", "friendship"], []),

    # ── Environment / Nature ──────────────────────────────────────────────────
    ("The Lorax", "Dr. Seuss", 4, 8, ["environment", "courage", "resilience"], []),
    ("Hoot", "Carl Hiaasen", 9, 13, ["environment", "courage", "problem_solving"], []),
    ("Flush", "Carl Hiaasen", 9, 13, ["environment", "courage", "family"], []),
    ("Scat", "Carl Hiaasen", 9, 13, ["environment", "problem_solving", "courage"], []),
    ("Seedfolks", "Paul Fleischman", 8, 12, ["diversity", "community", "environment"], []),
    ("The One and Only Ivan", "Katherine Applegate", 8, 12, ["courage", "friendship", "environment"], ["Newbery Medal 2013"]),
    ("Watership Down", "Richard Adams", 10, 14, ["courage", "friendship", "environment"], []),
    ("My Side of the Mountain", "Jean Craighead George", 9, 13, ["resilience", "environment", "courage"], ["Newbery Honor 1960"]),
    ("Julie of the Wolves", "Jean Craighead George", 9, 13, ["resilience", "environment", "courage"], ["Newbery Medal 1973"]),
    ("Island of the Blue Dolphins", "Scott O'Dell", 9, 12, ["resilience", "courage", "environment"], ["Newbery Medal 1961"]),
    ("Call of the Wild", "Jack London", 10, 14, ["courage", "resilience", "environment"], []),
    ("White Fang", "Jack London", 10, 14, ["courage", "resilience", "environment"], []),
    ("Old Yeller", "Fred Gipson", 8, 12, ["family", "courage", "resilience"], []),
    ("Ronia, the Robber's Daughter", "Astrid Lindgren", 8, 12, ["courage", "family", "environment"], []),
    ("The Sign of the Beaver", "Elizabeth George Speare", 9, 12, ["resilience", "history", "friendship"], ["Newbery Honor 1984"]),
]


# ── Google Books lookup ────────────────────────────────────────────────────────

async def fetch_google_books(client: httpx.AsyncClient, title: str, author: str):
    query = f'intitle:"{title}" inauthor:"{author.split()[0] if author else ""}"'
    params = {"q": query, "maxResults": 1, "printType": "books"}
    if GOOGLE_BOOKS_KEY:
        params["key"] = GOOGLE_BOOKS_KEY
    try:
        r = await client.get(
            "https://www.googleapis.com/books/v1/volumes",
            params=params, timeout=10.0
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return None
        info = items[0].get("volumeInfo", {})
        isbn_13, isbn_10 = None, None
        for id_obj in info.get("industryIdentifiers", []):
            if id_obj["type"] == "ISBN_13":
                isbn_13 = id_obj["identifier"]
            elif id_obj["type"] == "ISBN_10":
                isbn_10 = id_obj["identifier"]
        cover = (info.get("imageLinks") or {}).get("thumbnail")
        if cover:
            cover = cover.replace("http://", "https://").replace("zoom=1", "zoom=2")
        return {
            "google_books_id": items[0].get("id"),
            "isbn_13": isbn_13,
            "isbn_10": isbn_10,
            "description": info.get("description"),
            "page_count": info.get("pageCount"),
            "cover_url": cover,
            "published_year": int(info.get("publishedDate", "0")[:4]) if info.get("publishedDate") else None,
            "publisher": info.get("publisher"),
            "genres": info.get("categories", []),
        }
    except Exception:
        return None


# ── Claude goal classification ──────────────────────────────────────────────────

async def classify_goals_with_claude(client, title: str, author: str, description: str, seed_goals: list) -> list:
    """Use Claude Haiku to validate/extend goals from description."""
    if not ANTHROPIC_API_KEY or not description:
        return seed_goals

    prompt = f"""Children's book: "{title}" by {author}

Description: {description[:600]}

Current tags: {seed_goals}

From this list of learning goals, pick the 2-4 that best fit this book:
kindness, courage, friendship, emotions, science, history, diversity, resilience, problem_solving, environment, family, creativity

Return ONLY a JSON array of goal strings. Example: ["courage", "friendship"]
No explanation, just the JSON array."""

    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        # Extract JSON array
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m:
            goals = json.loads(m.group())
            validated = [g for g in goals if g in VALID_GOALS]
            return validated if validated else seed_goals
    except Exception:
        pass
    return seed_goals


# ── Database operations ───────────────────────────────────────────────────────

async def book_exists(conn, title: str):
    """Check if book exists by title (case-insensitive). Returns (exists, row)."""
    row = await conn.fetchrow(
        "SELECT id, cover_url, description, learning_goals FROM books WHERE LOWER(title) = LOWER($1)",
        title
    )
    return (row is not None), row


async def insert_or_enrich(conn, book: dict) -> str:
    """Insert new book or enrich existing one with missing metadata. Returns 'inserted'|'enriched'|'skipped'."""
    exists, existing = await book_exists(conn, book["title"])

    if exists:
        updates = {}
        if not existing["cover_url"] and book.get("cover_url"):
            updates["cover_url"] = book["cover_url"]
        if not existing["description"] and book.get("description"):
            updates["description"] = book["description"]
        # Merge learning goals
        current_goals = json.loads(existing["learning_goals"] or "[]")
        new_goals = book.get("learning_goals", [])
        merged = list(set(current_goals) | set(new_goals))
        if set(merged) != set(current_goals):
            updates["learning_goals"] = json.dumps(merged)

        if updates:
            set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
            vals = list(updates.values())
            await conn.execute(
                f"UPDATE books SET {set_clause} WHERE LOWER(title) = LOWER($1)",
                book["title"], *vals
            )
            return "enriched"
        return "skipped"

    # Insert new book
    try:
        await conn.execute("""
            INSERT INTO books (
                title, author, age_min, age_max,
                cover_url, description, page_count,
                published_year, publisher, genres,
                isbn_13, isbn_10, google_books_id,
                learning_goals, is_children_book, awards,
                is_series, has_violence, has_scary_content, has_adult_themes,
                language
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,
                $11,$12,$13,$14::jsonb,TRUE,$15::jsonb,
                FALSE,FALSE,FALSE,FALSE,'en'
            )
            ON CONFLICT DO NOTHING
        """,
            book["title"], book["author"], book["age_min"], book["age_max"],
            book.get("cover_url"), book.get("description"), book.get("page_count"),
            book.get("published_year"), book.get("publisher"),
            json.dumps(book.get("genres", [])),
            book.get("isbn_13"), book.get("isbn_10"), book.get("google_books_id"),
            json.dumps(book.get("learning_goals", [])),
            json.dumps(book.get("awards", []))
        )
        return "inserted"
    except Exception as e:
        print(f"    ❌ Insert failed for '{book['title']}': {e}")
        return "error"


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    from anthropic import AsyncAnthropic
    conn = await asyncpg.connect(DB_URL)
    anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

    before = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book = TRUE")
    print(f"BookMind Award Book Ingestion")
    print(f"Current children's books: {before}")
    print(f"Books to process: {len(CURATED_BOOKS)}")
    print(f"Google Books API: {'with key' if GOOGLE_BOOKS_KEY else 'keyless (rate-limited)'}")
    print(f"Claude goal classification: {'enabled' if anthropic_client else 'disabled'}\n")

    inserted = enriched = skipped = errors = 0
    last_request_time = 0

    async with httpx.AsyncClient() as http:
        # Deduplicate the curated list by title
        seen_titles = set()
        unique_books = []
        for entry in CURATED_BOOKS:
            t = entry[0].lower()
            if t not in seen_titles:
                seen_titles.add(t)
                unique_books.append(entry)

        print(f"Unique titles to process: {len(unique_books)}\n")

        for i, (title, author, age_min, age_max, seed_goals, awards) in enumerate(unique_books, 1):
            print(f"[{i:3}/{len(unique_books)}] {title[:50]}", end="", flush=True)

            # Rate-limit Google Books (max ~10 req/s without key)
            elapsed = time.time() - last_request_time
            if elapsed < 0.15:
                await asyncio.sleep(0.15 - elapsed)

            google = await fetch_google_books(http, title, author)
            last_request_time = time.time()

            goals = seed_goals
            if anthropic_client and google and google.get("description"):
                goals = await classify_goals_with_claude(
                    anthropic_client, title, author, google["description"], seed_goals
                )
                await asyncio.sleep(0.1)  # Claude rate limit buffer

            book = {
                "title": title,
                "author": author,
                "age_min": age_min,
                "age_max": age_max,
                "learning_goals": goals,
                "awards": awards,
                **(google or {}),
            }

            result = await insert_or_enrich(conn, book)
            if result == "inserted":
                inserted += 1
                print(f"  ✅ inserted")
            elif result == "enriched":
                enriched += 1
                print(f"  🔄 enriched")
            elif result == "skipped":
                skipped += 1
                print(f"  ⏭  skipped")
            else:
                errors += 1
                print(f"  ❌ error")

    after = await conn.fetchval("SELECT COUNT(*) FROM books WHERE is_children_book = TRUE")
    await conn.close()

    print(f"\n{'='*55}")
    print(f"DONE")
    print(f"  Inserted:  {inserted}")
    print(f"  Enriched:  {enriched}")
    print(f"  Skipped:   {skipped}")
    print(f"  Errors:    {errors}")
    print(f"  Children's books: {before} → {after} (+{after - before})")


if __name__ == "__main__":
    asyncio.run(main())
